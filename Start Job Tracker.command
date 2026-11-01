#!/bin/zsh
cd "${0:A:h}"
/usr/bin/python3 manage.py start && open http://localhost:3005
