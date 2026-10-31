"""
Módulo de Cálculo de Índices Espectrales de Vegetación y Agua.
Implementa NDVI, NDRE, EVI, SAVI y NDMI con estabilidad numérica y filtrado de píxeles inválidos.
"""

from typing import Dict, Optional
import numpy as np

from src.config import PipelineConfig

class VegetationIndices:
    """Calcula índices biofísicos y agronómicos a partir de bandas de reflectancia calibradas."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

    @staticmethod
    def _safe_normalized_difference(band_a: np.ndarray, band_b: np.ndarray) -> np.ndarray:
        """
        Calcula de forma numéricamente estable (A - B) / (A + B).
        Asigna np.nan donde el denominador es cero o alguno de los valores es NaN.
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            denominator = band_a + band_b
            numerator = band_a - band_b
            index = np.where(denominator != 0, numerator / denominator, np.nan)
            # Acotar físicamente a [-1.0, 1.0]
            index = np.clip(index, -1.0, 1.0)
        return index.astype(np.float32)

    def calculate_ndvi(self, red: np.ndarray, nir: np.ndarray, valid_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Índice de Vegetación de Diferencia Normalizada (NDVI).
        NDVI = (NIR - Red) / (NIR + Red)
        """
        ndvi = self._safe_normalized_difference(nir, red)
        if valid_mask is not None:
            ndvi[~valid_mask] = np.nan
        return ndvi

    def calculate_ndre(self, rededge: np.ndarray, nir: np.ndarray, valid_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Normalized Difference Red Edge (NDRE).
        Especial para cultivos densos donde el canal Rojo se satura por alta absorción de clorofila.
        NDRE = (NIR - RedEdge) / (NIR + RedEdge)
        """
        ndre = self._safe_normalized_difference(nir, rededge)
        if valid_mask is not None:
            ndre[~valid_mask] = np.nan
        return ndre

    def calculate_savi(self, red: np.ndarray, nir: np.ndarray, valid_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Soil-Adjusted Vegetation Index (SAVI).
        SAVI = ((NIR - Red) / (NIR + Red + L)) * (1 + L)
        Atenúa la influencia del brillo del suelo en cultivos jóvenes o abiertos.
        """
        l = self.config.savi_l_factor
        with np.errstate(divide="ignore", invalid="ignore"):
            denominator = nir + red + l
            numerator = nir - red
            savi = np.where(denominator != 0, (numerator / denominator) * (1.0 + l), np.nan)
            savi = np.clip(savi, -1.0, 1.0)
        if valid_mask is not None:
            savi[~valid_mask] = np.nan
        return savi.astype(np.float32)

    def calculate_evi(
        self,
        blue: np.ndarray,
        red: np.ndarray,
        nir: np.ndarray,
        valid_mask: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Enhanced Vegetation Index (EVI).
        EVI = G * (NIR - Red) / (NIR + C1*Red - C2*Blue + L)
        Alta sensibilidad en áreas de alta biomasa y resistencia a aerosoles atmosféricos.
        """
        g = self.config.evi_g_factor
        c1 = self.config.evi_c1_factor
        c2 = self.config.evi_c2_factor
        l = self.config.evi_l_factor

        with np.errstate(divide="ignore", invalid="ignore"):
            denominator = nir + (c1 * red) - (c2 * blue) + l
            numerator = nir - red
            evi = np.where(denominator != 0, g * (numerator / denominator), np.nan)
            evi = np.clip(evi, -1.0, 1.0)

        if valid_mask is not None:
            evi[~valid_mask] = np.nan
        return evi.astype(np.float32)

    def calculate_ndmi(self, nir: np.ndarray, swir: np.ndarray, valid_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Normalized Difference Moisture Index (NDMI / NDWI Gao).
        NDMI = (NIR - SWIR) / (NIR + SWIR)
        Monitorea el contenido de agua en la estructura celular de las hojas (estrés hídrico).
        """
        ndmi = self._safe_normalized_difference(nir, swir)
        if valid_mask is not None:
            ndmi[~valid_mask] = np.nan
        return ndmi

    def calculate_all(
        self,
        bands: Dict[str, np.ndarray],
        valid_mask: Optional[np.ndarray] = None
    ) -> Dict[str, np.ndarray]:
        """Calcula todos los índices viables según las bandas disponibles en el diccionario."""
        results = {}
        red = bands.get("red")
        nir = bands.get("nir")

        if red is not None and nir is not None:
            results["ndvi"] = self.calculate_ndvi(red, nir, valid_mask)
            results["savi"] = self.calculate_savi(red, nir, valid_mask)

        blue = bands.get("blue")
        if blue is not None and red is not None and nir is not None:
            results["evi"] = self.calculate_evi(blue, red, nir, valid_mask)

        rededge = bands.get("rededge")
        if rededge is not None and nir is not None:
            results["ndre"] = self.calculate_ndre(rededge, nir, valid_mask)

        swir = bands.get("swir")
        if swir is not None and nir is not None:
            results["ndmi"] = self.calculate_ndmi(nir, swir, valid_mask)

        return results
