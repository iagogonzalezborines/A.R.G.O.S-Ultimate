import re
import unicodedata

from .models import Decision


def normalize(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                           if not unicodedata.combining(c)).split()).strip(" .?!¿¡")


class Router:
    """Conservative fast paths. Unresolved language goes to one interpreter."""

    def resolve(self, text):
        value = normalize(text)
        value = re.sub(r"^argos[, :] *", "", value)
        value = re.sub(r"^(?:por favor|please)[, ]+", "", value)
        exact = {
            "hola": ("greeting", "Hola."),
            "hello": ("greeting", "Hello."),
            "hi": ("greeting", "Hello."),
            "buenas": ("greeting", "Buenas."),
            "gracias": ("greeting", "De nada."),
            "thanks": ("greeting", "You're welcome."),
            "que puedes hacer": ("capabilities", ""),
            "what can you do": ("capabilities", ""),
            "capacidades": ("capabilities", ""),
            "agentes": ("agents", ""),
            "agents": ("agents", ""),
            "lista los proyectos": ("projects", ""),
            "listar proyectos": ("projects", ""),
            "list projects": ("projects", ""),
            "proyectos": ("projects", ""),
            "que estas haciendo": ("status", ""),
            "como van las tareas": ("status", ""),
            "que esta haciendo codex": ("status", ""),
            "what are you working on": ("status", ""),
            "estado": ("status", ""),
            "status": ("status", ""),
            "activa modo gaming": ("gaming_on", ""),
            "activa el modo gaming": ("gaming_on", ""),
            "activate gaming mode": ("gaming_on", ""),
            "desactiva modo gaming": ("gaming_off", ""),
            "desactiva el modo gaming": ("gaming_off", ""),
            "deactivate gaming mode": ("gaming_off", ""),
            "silencio": ("stop_speech", ""),
            "deja de hablar": ("stop_speech", ""),
            "stop speaking": ("stop_speech", ""),
            "actualizate": ("maintenance", ""),
            "actualiza argos": ("maintenance", ""),
            "update yourself": ("maintenance", ""),
            "update argos": ("maintenance", ""),
        }
        if value in exact:
            kind, speech = exact[value]
            return Decision(kind, speech, reason="known_complete_intent")
        if value in ("informacion del sistema", "estado del pc", "system info", "inspect computer"):
            return Decision("capability", agent="computer", capability="system.info")
        if value in ("inspecciona el proyecto", "analiza el repositorio", "inspect repository", "inspect project"):
            return Decision("capability", agent="engineering", capability="repo.inspect")
        # The complete command must match. Do not turn quoted/negated sentences into effects.
        m = re.fullmatch(r"(?:inspecciona|analiza|revisa|inspect|review)\s+(?:el\s+)?(?:stl|gcode)\s+(.+)",
                         text.strip(), re.I)
        if m:
            filename = m[1].strip().strip('"')
            suffix = filename.rsplit(".", 1)[-1].lower()
            if suffix in ("stl", "gcode"):
                return Decision("capability", agent="design3d" if suffix == "stl" else "printing3d",
                                capability=f"{suffix}.inspect", arguments={"file": filename})
        # Explicit specialist addressing preserves the exact objective.
        m = re.match(r"^(engineering|programacion|computer|pc|design3d|diseno 3d|printing3d|impresion 3d):\s*\S", value)
        if m:
            agent = {"programacion": "engineering", "pc": "computer", "diseno 3d": "design3d",
                     "impresion 3d": "printing3d"}.get(m[1], m[1])
            return Decision("delegate", agent=agent, reason="explicit_specialist")
        # Obvious imperative domain requests bypass General, but never imply that
        # an unconnected operation can actually execute.
        if re.match(r"^(?:corrige|depura|implementa|programa|fix|debug|implement)\b", value):
            return Decision("delegate", agent="engineering", reason="clear_engineering_intent")
        if re.match(r"^(?:disena|modela|design|model)\b", value):
            return Decision("delegate", agent="design3d", reason="clear_design_intent")
        if re.match(r"^(?:imprime|print)\s+(?:en 3d|3d|la pieza|the model)\b", value):
            return Decision("delegate", agent="printing3d", reason="clear_printing_intent")
        return Decision("interpret", reason="local_resolution_insufficient")
