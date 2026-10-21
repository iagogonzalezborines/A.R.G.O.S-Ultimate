import re
import unicodedata

from .models import Decision
from .language import language_command


def normalize(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                           if not unicodedata.combining(c)).split()).strip(" .?!¿¡")


class Router:
    """Conservative fast paths. Unresolved language goes to one interpreter."""

    def resolve(self, text):
        language = language_command(text)
        if language:
            return Decision("language", arguments={"language": language}, reason="explicit_language_request")
        # Strip invocation prefixes from the original text too, preserving path
        # and app-name case for direct capabilities. They must not need Codex.
        text = re.sub(r"^argos[, :]+\s*", "", text.strip(), flags=re.I)
        text = re.sub(r"^(?:por favor|please)[, ]+", "", text, flags=re.I)
        value = normalize(text)
        review = re.fullmatch(r"(?:revisa (?:la )?aprobacion|review approval)(?: ([a-f0-9]{8,32}))?", value)
        if review:
            return Decision("approval_review", arguments={"task_id": review[1] or ""})
        confirm = re.fullmatch(r"(?:aprueba|approve)[:, ]+([a-z ,;]+)", value)
        if confirm:
            code = " ".join(re.split(r"[ ,;]+", confirm[1].strip(" ,;")))
            return Decision("approval_confirm", arguments={"code": code})
        if re.match(r"^(?:investiga|investigar|research|investigate)\b", value):
            return Decision("delegate", agent="research", reason="research_request")
        panel = re.sub(r"[, ]+(?:por favor|please)$", "", value)
        panel = re.sub(r"^(?:(?:puedes|podrias)(?: por favor)? |(?:can|could|would) you(?: please)? )", "", panel)
        if re.fullmatch(
                r"(?:(?:muestrame|muestra|mostrarme|mostrar|abre|abreme|abrir|abrirme|ver|ensename)(?: a)? |"
                r"(?:quiero|me gustaria) (?:ver|abrir) )?(?:los |el )?"
                r"(?:mapa(?: cerebral)? de (?:los )?agentes|diagrama de (?:los )?agentes|agentes)"
                r"(?: de argos)?(?: aqui| en (?:la |otra )?consola)?", panel):
            return Decision("panel", arguments={"view": "agents"})
        if re.fullmatch(
                r"(?:(?:muestrame|muestra|mostrarme|mostrar|abre|abreme|abrir|abrirme|ver|ensename) |"
                r"(?:quiero|me gustaria) (?:ver|abrir) )?(?:el |las )?"
                r"(?:monitor de tareas|panel de tareas|historial de tareas|registro de tareas|log de tareas|"
                r"log de tasks|tareas|conversaciones de codex)", panel):
            return Decision("panel", arguments={"view": "tasks"})
        if re.fullmatch(r"(?:(?:show|open)(?: me)? )?(?:the )?(?:argos )?"
                        r"(?:agents|agent map|agent diagram|(?:map|diagram) of (?:the )?(?:argos )?agents)"
                        r"(?: here| in (?:the |another )?console)?", panel):
            return Decision("panel", arguments={"view": "agents"})
        if re.fullmatch(r"(?:show|open)(?: me)? (?:the )?(?:task monitor|task log|task history|tasks|codex conversations)", panel):
            return Decision("panel", arguments={"view": "tasks"})
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
        if value in ("inspecciona el equipo", "inventario del equipo", "inspecciona el sistema",
                     "inspect system", "system inventory"):
            return Decision("capability", agent="computer", capability="system.inspect")
        if value in ("inspecciona el proyecto", "analiza el repositorio", "inspect repository", "inspect project"):
            return Decision("capability", agent="engineering", capability="repo.inspect")
        for names, capability, agent, arguments in (
            (("lista las aplicaciones", "listar aplicaciones", "list apps"), "apps.list", "computer", {}),
            (("lista las ventanas", "listar ventanas", "list windows"), "windows.list", "computer", {}),
            (("lista los archivos", "listar archivos", "list files"), "files.list", "engineering", {"path": "."}),
        ):
            if value in names:
                return Decision("capability", agent=agent, capability=capability, arguments=arguments)
        m = re.fullmatch(r"(?:busca en (?:la )?web|busca en internet|search the web for)\s+(.+)",
                         text.strip().rstrip(".?!"), re.I)
        if m:
            return Decision("capability", agent="research", capability="web.search", arguments={"query": m[1]})
        m = re.fullmatch(r"(?:abre|abrir|open)\s+(.+)", text.strip().rstrip(".?!"), re.I)
        if m:
            from .linux_tools import find_app
            from .models import ArgosError
            try:
                app = find_app(m[1])
                return Decision("capability", agent="computer", capability="apps.open",
                                arguments={"app": app["id"]})
            except ArgosError:
                pass
        m = re.fullmatch(r"(?:enfoca|focus)\s+(.+)", text.strip().rstrip(".?!"), re.I)
        if m:
            return Decision("capability", agent="computer", capability="windows.focus",
                            arguments={"window": m[1]})
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
        m = re.match(r"^(engineering|programacion|computer|pc|research|investigacion|design3d|diseno 3d|printing3d|impresion 3d):\s*\S", value)
        if m:
            agent = {"programacion": "engineering", "pc": "computer", "diseno 3d": "design3d",
                     "impresion 3d": "printing3d", "investigacion": "research"}.get(m[1], m[1])
            return Decision("delegate", agent=agent, reason="explicit_specialist")
        # Obvious imperative domain requests bypass General, but never imply that
        # an unconnected operation can actually execute.
        if re.match(r"^(?:corrige|depura|implementa|programa|fix|debug|implement)\b", value):
            if re.search(r"\b(?:en ti mismo|en tu propio (?:codigo|sistema)|en argos|in your own (?:code|system)|in argos|in yourself)\b", value):
                return Decision("develop", arguments={"target": "self"}, reason="explicit_self_development")
            return Decision("delegate", agent="engineering", reason="clear_engineering_intent")
        if re.match(r"^(?:disena|modela|design|model)\b", value):
            return Decision("delegate", agent="design3d", reason="clear_design_intent")
        if re.match(r"^(?:imprime|print)\s+(?:en 3d|3d|la pieza|the model)\b", value):
            return Decision("delegate", agent="printing3d", reason="clear_printing_intent")
        return Decision("interpret", reason="local_resolution_insufficient")
