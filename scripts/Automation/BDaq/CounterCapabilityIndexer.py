#!/usr/bin/python
# -*- coding:utf-8 -*-

from scripts.Automation.BDaq.CounterIndexer import CounterIndexer
from scripts.Automation.BDaq import CounterCapability
from scripts.Automation.BDaq import Utils


class CounterCapabilityIndexer(CounterIndexer):
    def __init__(self, nativeIndexer):
        super(CounterCapabilityIndexer, self).__init__(nativeIndexer, CounterCapability, Utils.toCounterCapability)
