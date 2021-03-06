#!/usr/bin/env python

"""
ocunit2junit - A Python script that generate a JUnit's XML file. This allows you to use that
on continuos integration servers like Jenkins, Hudson, QuickBuild with complete test reports.

https://github.com/vinyguitar/ocunit2junit

"""

import os
import re
import sys
import socket
import shutil
import unittest
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

__version__ = '0.1.2'
__author__ = 'Vinicius Freitas'

test_report_folder = "junit_report"

class InputParser():
    def __init__(self, input_buffer):
        self.input_buffer = input_buffer.split("\n")
        self.ended_current_test_suite = True
        self.test_case = None
        self.last_description = None
        self.total_passed_test_cases = 0
        self.tests_results = {}
        self.cur_test_duration = 0.0
        self.exit_code = 0

        if os.path.exists(test_report_folder):
            shutil.rmtree(test_report_folder)
        os.mkdir(test_report_folder)

    def _clean_input_buffer(self):
        for index, row in enumrate(self.input_buffer):
            if "octest" in row:
                del self.input_buffer[index]

    def parse_input(self):
        description = None
        self.time_format = '%Y-%m-%d %H:%M:%S'
        for row in self.input_buffer:

            regex = re.compile("\s\'(.+)\'\s")
            description_results = regex.findall(row)
            if description_results:
                description = description_results[0]

            regex = re.compile("Test Suite '(\S+)'.*started at\s+(.*)")
            for result in regex.finditer(row):
                t = result.group(2).replace("+0000", "").strip()
                self.handle_start_test_suite(
                        result.group(1),
                        datetime.strptime(t, self.time_format))
                self.last_description = None

            regex = re.compile("Test Suite '(\S+)'.*(?:finished|passed|failed) at\s+(.*).")
            for result in regex.finditer(row):
                t = result.group(2).replace("+0000", "").strip()
                self.handle_end_test_suite(
                        result.group(1),
                        datetime.strptime(
                            t,
                            self.time_format))

            regex = re.compile("Test Case '-\[\S+\s+(\S+)\]' started.")
            for result in regex.finditer(row):
                self.test_case = result.group(1)
                self.last_description = None

            regex = re.compile("Test Case '-\[\S+\s+(\S+)\]' passed \((.*) seconds\)")
            for result in regex.finditer(row):
                test_case = self.get_test_case_name(result.group(1), self.last_description)
                test_case_duration = float(result.group(2))
                self.handle_test_passed(test_case, test_case_duration)
                self.test_case = None

            if row.find(": error: -") > 0: # fix to speedup the task
                regex = re.compile("(.*): error: -\[(\S+) (\S+)\] : (.*)")
                for result in regex.finditer(row):
                    error_location = escape(result.group(1), {"'": "&#39;"})
                    test_suite = result.group(2)
                    error_message = escape(result.group(4), {"'": "&#39;"})
                    test_case = self.get_test_case_name(result.group(3), description)
                    self.handle_test_error(test_suite, test_case, error_message, error_location)

            regex = re.compile("Test Case '-\[\S+ (\S+)\]' failed \((\S+) seconds\)")
            for result in regex.finditer(row):
                test_case = self.get_test_case_name(result.group(1), self.last_description)
                test_case_duration = result.group(2)
                self.handle_test_failed(test_case, test_case_duration)
                self.test_case = None

            regex = re.compile("BUILD FAILED")
            if regex.search(row):
                self.exit_code = 1

            if description:
                self.last_description = description

        self.handle_unfinished_test_suite()

    def handle_start_test_suite(self, test_name, start_time):
        self.total_failed_test_cases = 0
        self.total_passed_test_cases = 0
        self.tests_results = {}
        self.errors = {}
        self.ended_current_test_suite = False
        self.cur_test_name = test_name
        self.cur_start_time = start_time
        self.cur_test_duration = 0.0

    def handle_end_test_suite(self, test_name, end_time):
        if not self.ended_current_test_suite:
            with open(os.path.join(test_report_folder, "TEST-%s.xml" % test_name), "w") as current_file:
                host_name = socket.gethostname()
                test_name = test_name
                total_tests = self.total_failed_test_cases + self.total_passed_test_cases
                if end_time:
                    test_duration = end_time - self.cur_start_time
                    time_stamp = end_time.strftime(self.time_format)
                else:
                    test_duration = self.cur_test_duration
                    time_stamp = (self.cur_start_time + timedelta(seconds=self.cur_test_duration)).strftime(self.time_format)
                suite_info = "<testsuite errors='0' failures='%d' hostname='%s' name='%s' tests='%d' time='%s' timestamp='%s'>\n" % (
                        self.total_failed_test_cases,
                        host_name,
                        test_name,
                        total_tests,
                        str(test_duration),
                        time_stamp
                        )
                current_file.write("<?xml version='1.0' encoding='UTF-8' ?>\n")
                current_file.write(suite_info)
                for test in sorted(self.tests_results):
                    test_case = test
                    duration = self.tests_results[test_case]
                    current_file.write("<testcase classname='%s' name='%s' time='%s'" % (test_name, test_case, duration))
                    if self.errors.has_key(test_case):
                        print "test_errors[0]"
                        print self.errors[test_case][0]
                        print "test_errors[1]"
                        print self.errors[test_case][1]

                        message = self.errors[test_case][0]
                        location = self.errors[test_case][1]
                        current_file.write(">\n")
                        current_file.write("<failure message='%s' type='Failure'>%s</failure>\n" % (
                            message,
                            location
                            ))
                        current_file.write("</testcase>\n")
                    else:
                        current_file.write(" />\n")

                current_file.write("</testsuite>\n")
            self.ended_current_test_suite = True

    def handle_unfinished_test_suite(self):
        if not self.ended_current_test_suite:
            if self.test_case:
                self.handle_test_error(self.cur_test_name, self.test_case, "UNFINISHED", None)
                self.handle_test_failed(self.test_case, 0.0)
            self.handle_end_test_suite(self.cur_test_name, None)

    def handle_test_passed(self, test_case, test_case_duration):
        self.total_passed_test_cases += 1
        self.tests_results[test_case] = test_case_duration
        self.cur_test_duration += float(test_case_duration)

    def handle_test_error(self, test_suite, test_case, error_message, error_location):
        self.errors[test_case] = [error_message, error_location]

    def handle_test_failed(self, test_case, test_case_duration):
        self.total_failed_test_cases += 1
        self.tests_results[test_case] = test_case_duration
        self.cur_test_duration += float(test_case_duration)

    def get_test_case_name(self, test_case, description):
       #if description:
       #    print "DESCRIPTION " + description
       #    return description
       #else:
       #    print "TESTCASE " + test_case
       #    return test_case
       return test_case

class InputParserTest(unittest.TestCase):

    def test_report_parser(self):
        with open("test_buffer", "r") as test_buffer_file:
            report = InputParser(test_buffer_file.read())

        report.parse_input()
        self.assertTrue(report.total_passed_test_cases > 0)
        self.assertTrue(report.exit_code == 0)

if __name__ == "__main__":
#   unittest.main()
   if len(sys.argv) > 2:
       test_report_folder = sys.argv[2]
   with open(sys.argv[1], 'r') as log_buffer_file:
       report = InputParser(log_buffer_file.read())
   report.parse_input()
