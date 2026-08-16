#!/usr/bin/env bash
set +e

mkdir -p /logs/verifier
rm -f /logs/verifier/reward.json /logs/verifier/reward.txt

PYTHONPATH=/app/src python -m unittest discover \
  -s /tests \
  -p 'test_*.py' \
  -v
status=$?

if [ "$status" -eq 0 ]; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi

exit "$status"
