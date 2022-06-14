# zabbix-keystore-discovery
Python script made to monitor JVM keystore cert dates for Zabbix.
Only basic Python modules and zabbix_sender used.

NB! 
This script has been currently written for and tested with python2.7, but it should work with python3 also!

## How it works?
* Script scans keystore for cert aliases.
* Finds per alias cert dates for "valid from" and "valid until".
* Generates json string from found aliases (for zabbix discovery).
* Sends discovery (json string) to zabbix to create all item prototypes (zabbix_sender used).
* Updates created discovery items with unix timestamp values (zabbix_sender used).

Currently script only logs to stdout. 
config.json is required and file paths there should be configured before running script.

PS. 

To simulate empty password for keystore (_-storepass ""_) write "None" as keystore_pass value in config.
Leaving password empty in config ("") will not add -storepass to keytool execute.

## Usage
* run from linux command line:

    `python zabbix_discovery -k /path/to/keystore -c /path/to/config.json`


* crontab entry example:
    
    ```
    # monitor keystore certs with zabbix_sender (every morning @ 06:15)
    15 06 * * *     /usr/bin/python /data/scripts/keystore_discovery.py -k /data/tomcat/keystore.jks -c /data/scripts/config.json > /dev/null 2>&1
    ```
  
## Zabbix template setup
1. Create new template
   
    * _Zabbix -> Configuration -> Templates -> "Create template"_
        
        `Name: "JVM keystore"`
    

2. Create discovery rule for template

    * _Zabbix -> Template "JVM keystore" -> Create discovery rule_

        ```
        Name: keystore discovery
        Type: Zabbix trapper
        Key: jvm.keystore.discovery
        Keep lost resources period (in days): 30
        Enabled [x]
        ```

3. Create item prototypes

    `Template "JVM keystore" -> Discovery rules -> Item Prototypes -> create item prototype`
    * Cert "**valid from**" item prototype:
        ```
        Name: Cert: "{#KEYALIAS}" start date
        Type: Zabbix trapper
        Key: jvm.keystore.startdate[{#KEYALIAS}]
        Type of information: Numeric (unsigned)
        Data type: Decimal
        Units: unixtime
        Show value: As is
        Application: JVM_KEYSTORE
        Create enabled [x]
        Discover [x]
        ```
      
    * Cert "**valid until**" item prototype:
        ```
        Name: Cert: "{#KEYALIAS}" end date
        Type: Zabbix trapper
        Key: jvm.keystore.enddate[{#KEYALIAS}]
        Type of information: Numeric (unsigned)
        Data type: Decimal
        Units: unixtime
        Show value: As is
        Application: JVM_KEYSTORE
        Create enabled [x]
        Discover [x]
        ```
      
4. Create trigger prototypes (customize for your need)
    * Trigger: "**[warning] No data received for item in 3 days**":
        ```
        Name: Keystore cert "{#KEYALIAS}" no data received for item in last 3 days!
        Expression: 
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].nodata(3d)}=1
        Severity: Warning
        Create enabled: [x]
        Discovery: [x]
        ```
      
    * Trigger: "**[high] Cert start date in future**":
        ```
        Name: Keystore cert "{#KEYALIAS}" start date in future! Start date: {ITEM.LASTVALUE}
        Expression: 
            {JVM keystore:jvm.keystore.startdate[{#KEYALIAS}].last()}
            -
            {JVM keystore:jvm.keystore.startdate[{#KEYALIAS}].now()}>1s
        Severity: High
        Create enabled: [x]
        Discovery: [x]
        ```
      
    * Trigger: "**[high] Cert expired**":
        ```
        Name: Keystore cert "{#KEYALIAS}" is expired! Expiry date: {ITEM.LASTVALUE}
        Expression: 
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].now()}
            -
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].last()}>1s
        Severity: High
        Create enabled: [x]
        Discovery: [x]
        ```
      
    * Trigger: "**[average] Cert will expire in 7 days**":
        ```
        Name: Keystore cert "{#KEYALIAS}" will expire in 7 days! Expiry date: {ITEM.LASTVALUE}
        Expression: 
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].last()}
            -
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].now()}<7d
        Severity: Average
        Create enabled: [x]
        Discovery: [x]
        ```
        * **Trigger depends on**: "[high] Cert expired": 
          
            ```
            Dependencies -> Add prototype:
                JVM keystore: Keystore cert "{#KEYALIAS}" is expired! Expiry date: {ITEM.LASTVALUE}
            ```
          
    * Trigger: "**[warning] Cert will expire in 30 days**":
        ```
        Name: Keystore cert "{#KEYALIAS}" will expire in 30 days! Expiry date: {ITEM.LASTVALUE}
        Expression: 
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].last()}
            -
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].now()}<30d
        Severity: Warning
        Create enabled: [x]
        Discovery: [x]
        ```
        * **Trigger depends on**: "[average] Cert will expire in 7 days": 
          
            ```
            Dependencies -> Add prototype:
                JVM keystore: Keystore cert "{#KEYALIAS}" will expire in 7 days! Expiry date: {ITEM.LASTVALUE}
            ```
          
    * Trigger: "**[info] Cert will expire in 60 days**":
        ```
        Name: Keystore cert "{#KEYALIAS}" will expire in 60 days! Expiry date: {ITEM.LASTVALUE}
        Expression: 
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].last()}
            -
            {JVM keystore:jvm.keystore.enddate[{#KEYALIAS}].now()}<60d
        Severity: Information
        Create enabled: [x]
        Discovery: [x]
        ```
        * **Trigger depends on**: "[warning] Cert will expire in 30 days": 
          
            ```
            Dependencies -> Add prototype:
                JVM keystore: Keystore cert "{#KEYALIAS}" will expire in 30 days! Expiry date: {ITEM.LASTVALUE}
            ```

5. Start using template :)