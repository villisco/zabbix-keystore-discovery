#!/usr/bin/python2.7
"""
Zabbix script to monitor JVM keystore cert expiration dates.
Only basic Python2 modules and zabbix_sender used.

Author: villisco
"""
import sys
import os
import json
import logging
import argparse
import subprocess
import datetime
import time

LOG_LEVEL = logging.INFO

CERT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

POST_DISCOVERY_DELAY = 2 # delay between sending zabbix discovery and updating discovered items

required_conf = [
        'zabbix_sender',
        'zabbix_confd',
        'keytool',
        'keystore_pass',
        'zbx_key_discovery',
        'zbx_key_startdate',
        'zbx_key_enddate'
]


def read_args():
        parser = argparse.ArgumentParser()
        parser.add_argument("-k", "--keystore", required=True, help="Keystore file location")
        parser.add_argument("-c", "--config", required=True, help="Config file location")
        return parser.parse_args()

def check_file(file_path):
        if not os.path.isfile(file_path) or not os.access(file_path, os.R_OK):
                logging.error("File \"%s\" does not exist or no read permissions!" % file_path)
                exit(1)

def validate_config(func):
        def wrap(conf_file):
                json = func(conf_file)
                missing = [k for k in required_conf if k not in json]

                if missing:
                        logging.error("Required config settings missing in \"%s\"! Required: %s" % (config, ', '.join(required_conf)))
                        exit(1)
                return json
        return wrap

@validate_config
def read_config(conf_file):
        with open(conf_file) as f:
                conf = json.load(f)
                return conf["keystore_discovery"]

def exec_cmd(cmd):
        try:
                logging.debug("Exec cmd: %s" % cmd)
                result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
        except Exception as e:
                logging.error('Failed to exec cmd %s' % cmd)
                raise(e)

        return result


class Keystore:
        def __init__(self, config, keystore):
                self.config = config
                self.keystore = keystore
                self.certs = {}

        def keystore_cmd(self, cmd_suffix=None):
                cmd = "%s -v -list -keystore %s" % (self.config["keytool"], self.keystore)

                if config["keystore_pass"] == "None":
                        cmd = cmd + " -storepass \"\""
                elif len(config["keystore_pass"]) > 1:
                        cmd = cmd + " -storepass %s" % self.config["keystore_pass"]

                if cmd_suffix is not None:
                        cmd = cmd + cmd_suffix

                return exec_cmd(cmd)

        def find_aliases(self):
                return self.keystore_cmd(" | sed -n \'s/^alias name: \(.*\)$/\\1/ip\'").splitlines()

        def format_date(func):
                def wrapper(self, alias):
                        date_str = func(self, alias)
                        logging.debug("date before format: %s" % date_str)
                        date_str = datetime.datetime.strptime(date_str, '%a %b %d %H:%M:%S %Z %Y').strftime(CERT_DATE_FORMAT)
                        logging.debug("date after format: %s" % date_str)
                        return date_str

                return wrapper

        @format_date
        def find_start_date(self, alias):
                return self.keystore_cmd(" -alias \'%s\' | sed -n \'s/^valid from: \(.*\) until:.*$/\\1/ip\'" % alias).strip()

        @format_date
        def find_end_date(self, alias):
                return self.keystore_cmd(" -alias \'%s\' | sed -n \'s/^valid from: .* until: \(.*\)$/\\1/ip\'" % alias).strip()

        def convert_to_timestamp(self, date):
                return time.mktime(datetime.datetime.strptime(date, CERT_DATE_FORMAT).timetuple())

        def scan_keystore(self):
                logging.info("Keystore \"%s\" scan started!" % self.keystore)
                aliases = self.find_aliases()

                for alias in aliases:
                        logging.info("\"%s\" cert found (alias)" % alias)

                        start_date = self.find_start_date(alias)
                        end_date = self.find_end_date(alias)

                        logging.info("\"%s\" cert begins: %s" % (alias, start_date))
                        logging.info("\"%s\" cert ends: %s" % (alias, end_date))

                        self.certs[alias] = {
                                "start_date": self.convert_to_timestamp(start_date),
                                "end_date": self.convert_to_timestamp(end_date)
                        }

                logging.info("Keystore \"%s\" scan completed!" % self.keystore)


class Zabbix:
        def __init__(self, config):
                self.config = config

        def send(self, key, value):
                cmd = "%s -c %s -k %s -o \'%s\'" % (self.config["zabbix_sender"], self.config["zabbix_confd"], key, value)
                exec_cmd(cmd)

        def aliases_to_json(func):
                def wrapper(self, aliases):
                        items = ''
                        aliases_count = len(aliases)
                        for i, alias in enumerate(aliases):
                                key = '{"{#KEYALIAS}":"%s"},' % alias

                                if (i == aliases_count-1):
                                        key = key[:-1] # remove "," from last item ending - json syntax rule

                                items = items + key
                        json = '{"data":[%s]}' % items
                        func(self, json)
                return wrapper

        @aliases_to_json
        def send_discovery(self, aliases):
                logging.info("Sending Zabbix discovery for key \"%s\"" % self.config["zbx_key_discovery"])
                self.send(self.config["zbx_key_discovery"], aliases)

        def send_item(self, item_type, alias, date):
                if item_type == "start":
                        key = self.config["zbx_key_startdate"]
                if item_type == "end":
                        key = self.config["zbx_key_enddate"]

                key = key + '["%s"]' % alias
                logging.info("Updating Zabbix item key \"%s\"" % key)
                self.send(key, date)


if __name__ == "__main__":
        start_time = datetime.datetime.now()

        args = read_args()
        check_file(args.keystore)
        check_file(args.config)

        config = read_config(args.config)

        logging.basicConfig(
                stream=sys.stdout, # only print to console for now (no syslog)
                level=LOG_LEVEL,
                format='%(asctime)s [%(filename)s] [%(levelname)s]: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
        )

        k = Keystore(config, args.keystore)
        k.scan_keystore()

        z = Zabbix(config)
        z.send_discovery(k.certs.keys())

        logging.info("Waiting delay between discovery and updating items for \"%s\" seconds.." % POST_DISCOVERY_DELAY)
        time.sleep(POST_DISCOVERY_DELAY) # wait before items created by discovery

        for alias, data in k.certs.items():
                z.send_item("start", alias, data["start_date"])
                z.send_item("end", alias, data["end_date"])

        end_time = datetime.datetime.now() - start_time
        logging.info("Script exec time: %s" % end_time)
