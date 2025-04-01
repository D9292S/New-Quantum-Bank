release: bash heroku_scripts/release.sh && python heroku_scripts/check_optimizations.py
web: python launcher.py --performance high --cluster 1 --clusters 1
worker: python launcher.py --performance high --log-level verbose --cluster 1 --clusters 1 