"""The version of EcoDB: ONE place (#1362, Pepe's decision 139 of 23-nov: «the version we are running is the real
one», the ecodb-api image tag).

It is the tag of the ecodb-api image in docker-compose.yml (api, worker and ecodb-cell) and what /health says
(settings.API_VERSION). test_version.py fails if they disagree. Change it only with scripts/subir_version.py, which
moves the three tags too and opens the CHANGELOG section; when that section is on main, CI publishes the release.
Before 0.25.0 the public tags and releases used another numbering (v1.x): that one is history.
"""

__version__ = "0.25.0"
