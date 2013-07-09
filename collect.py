#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# collect.py - collect AWS dashboard information and store it in the
# file system
#
# (c) Santeri Paavolainen, Finland, 2013
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# This script is meant to be *robust*. It tries *not* to parse
# anything it does not have, and it stores all of the data it collects
# *as-is* (gzipped to save space).
#
# This program, by default, will load http://status.aws.amazon.com/,
# look up all URLs that look like RSS urls, fetch those RSS urls and
# store them in a timestamped subdirectory on directory saved/
# (--save-dir).
#
# If it fails to fetch the dashboard page (--dashboard-url), it will
# retry for 60 minutes (--timeout), and fail with an error if
# no successfull fetch occurs during that time. The failure is logged
# on stderr and program will exit with code 3.
#
# The same applies for RSS urls, but it will keep fetching them only
# up to 60 minutes (--timeout) from the start of the program. (That
# is, this program tries its darnest not to run longer than 1 hour.)
#
# Note that the program will work with the RSS urls in round-robin
# fashion, so if one fails, then it is retried only after all of the
# other RSS urls have been tried.
#
# If some RSS url cannot be retrieved, an error is printed out and
# program exits with error code 4.
#
# If less than 100 RSS feeds (--min-feeds) were found on the dashboard
# page, then after fetching the RSS feeds (with above rules, with
# timeout and retrieve errors honored) program will fail and exit with
# error code 5.
#
# If there's any other unexpected problem (exception, file cannot be
# opened, etc.) the program will print the error / exception trace and
# exit with code 1.
#
# This program tries to be *pedantic* about handling all above error
# cases to ensure it can be safely left to run in a crontab so that if
# you've got your email working correctly (for receiving errors from
# crontab jobs) you *will* get a sensible error report if anything
# fails.

from argparse import ArgumentParser
from sys import exit, stdout, stderr
from urlparse import urljoin
from requests import Session
from requests.exceptions import Timeout as RequestTimeout
from time import time, sleep
from datetime import datetime
from random import randrange
from traceback import print_exc
import re
import yaml
from os.path import join as join_path
from os import makedirs, rename
from collections import deque
from hashlib import sha256
import gzip

def get_parser():
    parser = ArgumentParser(description="""AWS dashboard data
collector. This program will fetch all RSS feeds listed in the AWS
Dashboard and store those in a given directory. This program is quiet
unless problems are encountered.
""")
    parser.add_argument('--dashboard-url', '-d', metavar='URL',
                        type=str,
                        default='http://status.aws.amazon.com/',
                        help='AWS dashboard URL')
    parser.add_argument('--timeout', '-t', metavar='TIMEOUT',
                        type=int, default=3600,
                        help='Program timeout in seconds')
    parser.add_argument('--min-feeds', '-m', metavar='COUNT',
                        type=int, default=150,
                        help='Minimum number of feeds expected to be found')
    parser.add_argument('--save-dir', '-s', metavar='DIRECTORY',
                        type=str, default="saved",
                        help='Directory where to save results')

    return parser

class GlobalTimeout(Exception):
    pass

class BadResponse(Exception):
    pass

def main():
    parser = get_parser()
    args = parser.parse_args()

    s = Session()
    start = time()

    def until(wait):
        result = min(wait, start + args.timeout - time())

        if result <= 0:
            raise GlobalTimeout()

        return result

    # Wrap all of the rest to catch any unexpected exception and
    # handle it cleanly.
    try:
        # Fetch dashboard page, watch for global timeout, handle
        # request timeouts
        try:
            while True:
                try:
                    # Random timeout, 60..300
                    r = s.get(args.dashboard_url,
                              timeout=until(randrange(60, 300)))

                    if r.status_code != 200:
                        raise BadResponse()

                    break
                except (RequestTimeout, BadResponse):
                    # This is expected...
                    pass
        except GlobalTimeout:
            print >>stderr, ("ERROR: Failed fetching %s within timeout of %d "
                             "seconds, exiting..." % (args.dashboard_url, args.timeout))
            exit(3)

        rss_urls = []
        rss_re = re.compile(r'(?i)href\s*=\s*[\'"](\S+?)[\'"]\s*')

        for m in rss_re.finditer(r.text):
            url = m.group(1)
            # Filter out those that don't end in .rss
            if not url.endswith('.rss'):
                continue

            rss_urls.append(urljoin(args.dashboard_url, url))

        # Determine where to put files, create directory if needed.
        save_dir = join_path(args.save_dir,
                             datetime.fromtimestamp(start).isoformat())

        makedirs(save_dir)

        # Start fetching URLs. Write results to a file in the
        # generated direcotry and after *each* file write, write a
        # YAML summary containing meta-information of the directory
        # contents.

        pending_urls = deque(rss_urls)
        result_set = {
            'rss_urls': map(lambda u: u.encode('utf-8'), rss_urls),
            'started': start,
            'dashboard_url': args.dashboard_url,
            'url_info': {}
            }

        rss_fetched = 0

        try:
            while len(pending_urls) > 0:
                url = pending_urls.popleft()
                timeout = until(randrange(10, 60))
                rss_start = time()

                try:
                    r = s.get(url, timeout=timeout)

                    if r.status_code != 200:
                        raise BadResponse()
                except (RequestTimeout, BadResponse):
                    pending_urls.append(url)
                    continue

                key = url.encode('utf-8')
                file_name = sha256((url + ":" + r.text).encode('utf-8')).hexdigest() + ".rss"
                now = time()

                result_set['url_info'][key] = {
                    'url': key,
                    'file': file_name,
                    'fetched': now,
                    'elapsed': now - rss_start,
                    'size': len(r.text),
                    }

                data_file = join_path(save_dir, file_name)
                meta_file = join_path(save_dir, "meta.yaml")

                with gzip.open(data_file + ".gz", "wb") as f:
                    f.write(r.text.encode('utf-8'))

                with gzip.open(meta_file + ".gz.tmp", "wb") as f:
                    f.write(yaml.dump(result_set))

                rename(meta_file + ".gz.tmp", meta_file + ".gz")

                rss_fetched += 1

        except GlobalTimeout:
            print >>stderr, ("ERROR: Could not fetch all RSS feeds "
                             "within the timeout limit. "
                             "Fetched %d feeds out of %d.") % (
                rss_fetched, len(rss_urls))
            exit(4)

        # Last step, if there were less than expected minimum number
        # of RSS urls, fail.
        if len(rss_urls) < args.min_feeds:
            print >>stderr, "ERROR: Found %d RSS feeds, less than expected minimum of %d." % (len(rss_urls), args.min_feeds)
            exit(5)
    except Exception, e:
        print >>stderr, "ERROR: Got unexpected exception: %s" % (e,)
        print_exc()
        exit(1)

    exit(0)

if __name__ == '__main__':
    main()
