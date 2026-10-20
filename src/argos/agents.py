from dataclasses import asdict, dataclass
from importlib.resources import files


@dataclass(frozen=True)
class Agent:
    id: str
    role: str
    capabilities: tuple[str, ...]
    contract: str


AGENTS = {
    a.id: a
    for a in (
        Agent("general", "Conversación e interpretación contextual", (), "ARGOS.md"),
        Agent("engineering", "Programación y mantenimiento", ("repo.inspect",), "ENGINEERING.md"),
        Agent("computer", "Manejo del PC", ("system.info",), "COMPUTER.md"),
        Agent("design3d", "Diseño y geometría 3D", ("stl.inspect",), "DESIGN3D.md"),
        Agent("printing3d", "Preparación e impresión 3D", ("gcode.inspect",), "PRINTING3D.md"),
    )
}


def contract(agent: str = "general") -> str:
    root = files("argos").joinpath("contracts")
    common = root.joinpath("ARGOS.md").read_text(encoding="utf-8")
    if agent != "general":
        common += "\n\n" + root.joinpath(AGENTS[agent].contract).read_text(encoding="utf-8")
    return common


def catalogue(provider: str = "none") -> list[dict]:
    return [
        {**asdict(a), "provider": provider, "execution": "local_capabilities",
         "intelligence": "not_configured" if provider == "none" else "configured_unverified"}
        for a in AGENTS.values()
    ]
