#!/bin/bash
# Monitor re-indexing progress
echo "Re-indexing Progress Monitor"
echo "=============================="
echo ""
tail -f /tmp/claude/-Users-hughferguson-repos-bort/tasks/b80d3f0.output 2>/dev/null | grep -E "(Indexing|Writing|Appending|indexed|Skipped)" --line-buffered
