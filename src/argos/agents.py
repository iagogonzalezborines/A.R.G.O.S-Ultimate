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
        Agent("engineering", "Programación y mantenimiento",
              ("system.inspect", "repo.inspect", "files.list", "files.read", "files.write", "commands.run", "web.search", "web.read", "files.stat", "files.list_page",
               "files.read_range", "files.patch", "files.mkdir", "files.copy", "files.move",
               "files.delete", "projects.create", "workspace.open", "commands.exec",
               "development.plan", "development.check", "development.review"), "ENGINEERING.md"),
        Agent("computer", "Manejo del PC",
              ("system.info", "system.inspect", "apps.list", "apps.open", "windows.list", "windows.focus",
               "windows.close", "files.open", "web.open", "files.list", "files.stat", "files.list_page",
               "files.read", "files.read_range", "files.write", "files.patch", "files.mkdir",
               "files.copy", "files.move", "files.delete", "projects.create", "workspace.open", "commands.exec"), "COMPUTER.md"),
        Agent("research", "Búsqueda web y fuentes", ("web.search", "web.read"), "RESEARCH.md"),
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


def local_contract(agent: str = "general") -> str:
    root = files("argos").joinpath("contracts")
    common = root.joinpath("ARGOS.md").read_text(encoding="utf-8")
    # One shared personality source; the local model does not need the full
    # architecture manual on every spoken turn.
    personality = common.split("## Personality\n", 1)[1].split("## Decide before acting", 1)[0]
    result = "# ARGOS interaction contract — local\n\nYou are ARGOS.\n" + personality
    result += "\n" + root.joinpath("LOCAL.md").read_text(encoding="utf-8")
    if agent != "general":
        result += "\n" + root.joinpath(AGENTS[agent].contract).read_text(encoding="utf-8")
    return result


def catalogue(provider: str = "none") -> list[dict]:
    return [
        {**asdict(a), "provider": provider, "execution": "local_capabilities",
         "intelligence": "not_configured" if provider == "none" else "configured_unverified"}
        for a in AGENTS.values()
    ]
