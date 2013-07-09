=========================
 AWS Dashboard Collector
=========================

This is a simple program with one purpose: *fetch AWS dashboard RSS
feeds and store them on a disk*.

To clarify, this program is only meant to **fetch** the data, but to
try to do it really, really stubbornly.

Why?

* I am collecting this information for later analysis. I've written a
  seminar paper on the topic of AWS availability based on AWS
  dashboard data -- I'll add link here when it gets published ...

* I relied on Google Reader to collect and store the data, but it had
  one obvious and one less obvious problem: Google Reader was closed
  down on July 1st 2013, and the it started collecting RSS feed data
  only after a feed was added by someone there -- thus there was a lag
  time between new RSS feeds added by AWS to the point when Google
  Reader started archiving them.

So that's why. I wrote this program with the intention to be as
reliable as possible, persistent enough not to fall over due to a
small network hiccup and to fail clearly.

I'm actually running this program on a Raspberry Pi, scheduled to run
twice a day with timeout of 10 hours. There's a secondary cron job
that regularly pushes the data to a S3 bucket (using s3cmd) as a
backup -- I've had SD cards fail suddenly, so I'm not taking any
chances.

Usage
=====

Simple:::

  ./collect.py

After the program finishes (it will not print out anything on success)
look for contents of directory ``saved``. There will be subdirectories
with timestamps as their names, which in turn contain actual RSS files
(``*.rss.gz``) and a metadata file in YAML format (``meta.yaml.gz``).

You can customize the script's behavior a bit -- look for options with
``./collect.py --help``.

And that's it.
