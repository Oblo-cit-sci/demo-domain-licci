import csv
from logging import getLogger
from os.path import dirname, join, isfile

from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.util.exceptions import ApplicationException

use_rasterio = True
logger = getLogger(__name__)
try:
    import rasterio
except ModuleNotFoundError as mnfe:
    logger.warning(
        f"Import problem in {__name__}. reason: {mnfe}. Fallback to low resolution backup"
    )
    use_rasterio = False

from app.util.plugins import BasePlugin

""" call

POST http://HOST/api/basic/plugin?plugin_name=koeppgen_geiger_classification
with body:

{
"coordinates": {
	"lon": 120,
	"lat": 49
	}
}

optional arguments:
"split": boolean, default True, results levels as array, otherwise comma separated in one string

##
curl -X POST "http://HOST/api/basic/plugin?plugin_name=koeppgen_geiger_classification" -H  "accept: application/json" -H  "Content-Type: application/json" -d "{\"coordinates\":{\"lon\":120,\"lat\":49}}"

or with precision:
curl -X POST "http://localhost:8100/api/basic/plugin?plugin_name=koeppgen_geiger_classification" -H  "accept: application/json" -H  "Content-Type: application/json" -d "{\"coordinates\":{\"lon\":120,\"lat\":49},\"precision\":1}"

"""


class KoeppenGeigerPlugin(BasePlugin):
    plugin_name = "koeppgen_geiger_classification"

    def __init__(self):
        global use_rasterio
        super().__init__()
        if use_rasterio:
            self.src_files = [
                join(dirname(__file__), "kgc_data", f)
                for f in [
                    "Beck_KG_V1_present_0p5.tif",
                    "Beck_KG_V1_present_0p083.tif",
                    "Beck_KG_V1_present_0p0083.tif",
                ]
            ]
            self.available_srces = []
            for (index, src_file) in enumerate(self.src_files):
                if not isfile(src_file):
                    logger.warning(f"cgk_plugin is missing file:{src_file}")
                    self.available_srces.append(False)
                else:
                    self.available_srces.append(True)
            if not any(self.available_srces):
                use_rasterio = False
                logger.warning(
                    "Non of the source files is available. Switching to low resolution backup"
                )

        if not use_rasterio:
            self.src_file = join(
                dirname(__file__), "kgc_data/Beck_KG_V1_present_0p5.tif.csv"
            )
            if not isfile(self.src_file):
                raise FileNotFoundError(f"cgk_plugin is missing file:{self.src_file}")
        # this values are only valid with 0p5
        self.transform = {
            "lat_ini": -89.75,
            "lon_ini": -179.75,
            "lon_cells": 720,
            "s": 0.5,
        }
        self.legend = {
            1: ["Af", "Tropical", "rainforest"],
            2: ["Am", "Tropical", "monsoon"],
            3: ["Aw", "Tropical", "savannah"],
            4: ["BWh", "Arid", "desert", "hot"],
            5: ["BWk", "Arid", "desert", "cold"],
            6: ["BSh", "Arid", "steppe", "hot"],
            7: ["BSk", "Arid", "steppe", "cold"],
            8: ["Csa", "Temperate", "dry summer", "hot summer"],
            9: ["Csb", "Temperate", "dry summer", "warm summer"],
            10: ["Csc", "Temperate", "dry summer", "cold summer"],
            11: ["Cwa", "Temperate", "dry winter", "hot summer"],
            12: ["Cwb", "Temperate", "dry winter", "warm summer"],
            13: ["Cwc", "Temperate", "dry winter", "cold summer"],
            14: ["Cfa", "Temperate", "no dry season", "hot summer"],
            15: ["Cfb", "Temperate", "no dry season", "warm summer"],
            16: ["Cfc", "Temperate", "no dry season", "cold summer"],
            17: ["Dsa", "Cold", "dry summer", "hot summer"],
            18: ["Dsb", "Cold", "dry summer", "warm summer"],
            19: ["Dsc", "Cold", "dry summer", "cold summer"],
            20: ["Dsd", "Cold", "dry summer", "very cold winter"],
            21: ["Dwa", "Cold", "dry winter", "hot summer"],
            22: ["Dwb", "Cold", "dry winter", "warm summer"],
            23: ["Dwc", "Cold", "dry winter", "cold summer"],
            24: ["Dwd", "Cold", "dry winter", "very cold winter"],
            25: ["Dfa", "Cold", "no dry season", "hot summer"],
            26: ["Dfb", "Cold", "no dry season", "warm summer"],
            27: ["Dfc", "Cold", "no dry season", "cold summer"],
            28: ["Dfd", "Cold", "no dry season", "very cold winter"],
            29: ["ET", "Polar", "tundra"],
            30: ["EF", "Polar", "frost"],
        }

    def __call__(self, *args, **kwargs):
        logger.debug("KoeppenGeigerPlugin called")
        if len(args) == 0 or type(args[0]) is not dict:
            raise ApplicationException(
                HTTP_422_UNPROCESSABLE_ENTITY,
                "Wrong input format. Pass a dict with coordinates:lon,lat",
            )

        try:
            lon = args[0]["coordinates"]["lon"]
            lat = args[0]["coordinates"]["lat"]
        except:
            raise ApplicationException(
                HTTP_422_UNPROCESSABLE_ENTITY,
                "Wrong format. Pass a dict with coordinates:lon,lat",
            )
        if use_rasterio:
            logger.debug("raster-io")
            code = self.read_from_rasterfile(lat, lon, args[0].get("precision", 0))
        else:
            logger.debug("from file")
            code = self.read_from_simple_file(lat, lon)

        classification = self.legend.get(code, None)
        if not classification:
            return {"value": []}

        code = classification[0]
        texts = classification[1:]
        value = [
            {"value": code[: i + 1], "text": text} for (i, text) in enumerate(texts)
        ]
        # split_levels = args[0].get("split", True)
        # if split_levels:
        #     value = [classification[0][0]] + classification  # first letter (used for tags) + full code + titles (english)
        # else:
        #     value = ", ".join(classification[2:])
        return {"value": value}

    def get_available_precision(self, precision):
        if precision == 0:
            return 0
        precision = min(precision, len(self.available_srces))
        for i in list(range(precision))[::-1]:
            if self.available_srces[i]:
                logger.debug(f"using precision {i}")
                return i

    def read_from_simple_file(self, lat, lon):
        # todo this does not seem to work properly
        with open(self.src_file) as fin:
            reader = csv.reader(fin)
            lat_s = int((lat - self.transform["lat_ini"]) / self.transform["s"])
            for i in range(lat_s - 1):
                next(reader)
            line = next(reader)
            lon_s = int((lon - self.transform["lon_ini"]) / self.transform["s"])
            return line[lon_s]

    def read_from_rasterfile(self, lat, lon, precision=0):
        precision = self.get_available_precision(precision)
        raster = rasterio.open(self.src_files[precision])
        index = raster.index(lon, lat)
        return raster.read(1)[index[0], index[1]]
