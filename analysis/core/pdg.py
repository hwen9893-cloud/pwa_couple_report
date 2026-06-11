"""PDG reference values for resonances used in the phi-hh analysis.

Each entry: (mass_GeV, mass_err, width_GeV, width_err).
Source: PDG 2024.
"""

import re

PDG: dict[str, tuple[float, float, float, float]] = {
    # Scalar mesons (f0)
    "f0(500)":  (0.400,  0.200, 0.500,  0.200),
    "f0(980)":  (0.990,  0.020, 0.060,  0.030),
    "f0(1370)": (1.350,  0.150, 0.350,  0.150),
    "f0(1500)": (1.522,  0.007, 0.108,  0.012),
    "f0(1710)": (1.733,  0.006, 0.150,  0.010),

    # Tensor mesons (f2)
    "f2(1270)": (1.2754, 0.0008, 0.1858, 0.0025),
    "f2(1430)": (1.430,  0.010,  0.046,  0.010),
    "f2(1525)": (1.5173, 0.0024, 0.072,  0.006),
    "f2(1565)": (1.571,  0.012,  0.132,  0.013),
    "f2(1810)": (1.815,  0.012,  0.197,  0.023),

    # Vector mesons (rho)
    "rho(1450)": (1.465, 0.025, 0.400, 0.060),
    "rho(1570)": (1.570, 0.010, 0.144, 0.030),
    "rho(1690)": (1.690, 0.010, 0.161, 0.010),

    # K1 axial
    "K1(1400)": (1.403, 0.007, 0.174, 0.013),

    # K2 tensor
    "K2(1820)": (1.819, 0.012, 0.264, 0.027),
    "K2(1980)": (1.990, 0.030, 0.348, 0.030),
    "K2(2250)": (2.247, 0.017, 0.180, 0.040),

    # K3
    "K3(2320)": (2.324, 0.024, 0.150, 0.040),
}


def _normalize(name: str) -> str:
    """Strip all non-alphanumeric characters and lowercase for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def pdg_lookup(param_name: str) -> tuple[float, float] | None:
    """Return (pdg_value, pdg_error) for a mass or width parameter name.

    Both the parameter name and PDG resonance key are normalized (all
    non-alphanumeric characters removed) before comparison, so
    ``f0_980_mass``, ``f0980mass``, and ``F0(980)_Mass`` all match ``f0(980)``.
    """
    norm_param = _normalize(param_name)
    for res, (m0, dm, g0, dg) in PDG.items():
        norm_res = _normalize(res)
        if norm_res in norm_param:
            if "mass" in norm_param:
                return m0, dm
            if "width" in norm_param:
                return g0, dg
    return None
