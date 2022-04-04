import json
from logging import getLogger

import httpx
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY, HTTP_404_NOT_FOUND

from app.settings import env_settings
from app.util.exceptions import ApplicationException
from app.util.plugins import BasePlugin

logger = getLogger(__name__)

"""

Include a doi key in the dict
e.g.
{"doi":"https://doi.org/10.1016/j.gloenvcha.2012.04.003"}

Example:

curl -X 'POST' \
  'http://localhost:8100/api/basic/plugin?plugin_name=crossref-call' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
"doi": "https://doi.org/10.1016/j.gloenvcha.2012.04.003"
}'


"""


class CrossRefPlugin(BasePlugin):
    plugin_name = "crossref-call"

    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        logger.debug("Crossref plugin called")
        if len(args) == 0 or type(args[0]) is not dict:
            raise ApplicationException(
                HTTP_422_UNPROCESSABLE_ENTITY, "Wrong input format"
            )
        try:
            doi = args[0]["doi"]
        except:
            raise ApplicationException(
                HTTP_422_UNPROCESSABLE_ENTITY,
                "Wrong format. Pass a dict with key: 'doi'",
            )
        resp = httpx.get(
            "https://api.crossref.org/v1/works/" + doi,
            params={"mailto": env_settings().FIRST_ADMIN_EMAIL},
        )
        if resp.status_code == HTTP_404_NOT_FOUND:
            raise ApplicationException(HTTP_404_NOT_FOUND, "No article under this doi")
        data = resp.json()
        if data["status"] != "ok":
            logger.error("Could not get crossref data")
            raise ApplicationException(
                HTTP_422_UNPROCESSABLE_ENTITY, "Could not obtain crossref data"
            )
        return data["message"]
