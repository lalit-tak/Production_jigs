#!/usr/bin/python
# -*- coding:utf-8 -*-

from scripts.Automation.BDaq.CounterIndexer import CounterIndexer
from scripts.Automation.BDaq import SignalDrop
from scripts.Automation.BDaq import Utils


class CounterGateSourceIndexer(CounterIndexer):
    def __init__(self, nativeIndexer):
        super(CounterGateSourceIndexer, self).__init__(nativeIndexer, SignalDrop, Utils.toSignalDrop)
