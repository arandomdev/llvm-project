# TestTsanSwift.py
#
# This source file is part of the Swift.org open source project
#
# Copyright (c) 2014 - 2016 Apple Inc. and the Swift project authors
# Licensed under Apache License v2.0 with Runtime Library Exception
#
# See https://swift.org/LICENSE.txt for license information
# See https://swift.org/CONTRIBUTORS.txt for the list of Swift project authors
#
# ------------------------------------------------------------------------------
"""
Test that the TSan support correctly reports Swift access races (races on
mutating methods of a struct).
"""
import lldb
from lldbsuite.test.decorators import *
import lldbsuite.test.lldbtest as lldbtest
import lldbsuite.test.lldbutil as lldbutil
import os
import unittest2
import json


class TsanSwiftAccessRaceTestCase(lldbtest.TestBase):

    mydir = lldbtest.TestBase.compute_mydir(__file__)

    @swiftTest
    @skipIfLinux
    @skipUnlessSwiftThreadSanitizer
    @skipIfAsan # This test does not behave reliable with an ASANified LLDB.
    @skipIfDarwinEmbedded
    def test_tsan_swift(self):
        self.build()
        self.do_test()

    def setUp(self):
        lldbtest.TestBase.setUp(self)
        self.main_source = "main.swift"
        self.main_source_spec = lldb.SBFileSpec(self.main_source)

    def do_test(self):
        exe_name = "a.out"
        exe = self.getBuildArtifact(exe_name)

        # Create the target
        target = self.dbg.CreateTarget(exe)
        self.assertTrue(target, lldbtest.VALID_TARGET)

        runtimes = []
        for m in target.module_iter():
            libspec = m.GetFileSpec()
            if "clang_rt" in libspec.GetFilename():
                runtimes.append(os.path.join(libspec.GetDirectory(), libspec.GetFilename()))
        self.registerSharedLibrariesWithTarget(target, runtimes)

        self.runCmd("run")

        stop_reason = self.dbg.GetSelectedTarget().process.GetSelectedThread().GetStopReason()
        if stop_reason == lldb.eStopReasonExec:
            # On OS X 10.10 and older, we need to re-exec to enable
            # interceptors.
            self.runCmd("continue")

        # the stop reason of the thread should be a TSan report.
        self.expect("thread list", "A Swift access race should be detected",
                    substrs=['stopped', 'stop reason = Swift access race detected'])

        self.assertEqual(
            self.dbg.GetSelectedTarget().process.GetSelectedThread().GetStopReason(),
            lldb.eStopReasonInstrumentation)

        self.expect(
            "thread info -s",
            "The extended stop info should contain the TSan provided fields",
            substrs=[
                "instrumentation_class",
                "description",
                "mops"])

        output_lines = self.res.GetOutput().split('\n')
        json_line = '\n'.join(output_lines[2:])
        data = json.loads(json_line)
        self.assertEqual(data["instrumentation_class"], "ThreadSanitizer")
        self.assertEqual(data["issue_type"], "external-race")
        self.assertEqual(len(data["mops"]), 2)
        self.assertTrue(data["location_filename"].endswith("/main.swift"))

