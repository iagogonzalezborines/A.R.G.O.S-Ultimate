"""Spanish/English turn selection. Short lexical evidence beats uncertain audio guesses."""
import re
import unicodedata


def normalized(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                           if not unicodedata.combining(c)).split()).strip(" .?!¿¡")


def language_command(text):
    value = normalized(text)
    value = re.sub(r"^argos[, :] *", "", value)
    value = re.sub(r"^(?:por favor|please)[, ]+", "", value)
    value = re.sub(r"[, ]+(?:por favor|please)$", "", value)
    value = " ".join(value.replace(",", " ").split())
    spanish = (r"(?:(?:puedes|podrias|quiero que|me gustaria que)\s+)?(?:me )?"
               r"(?:habla|hablame|hablar|hablarme|hables|hablas|responde|respondeme|"
               r"responder|respondas|contesta|contestame|contestar|contestes|cambia|cambiar|cambies|pasate)"
               r"(?: el idioma| de idioma)? (?:en |a |al )?(ingles|espanol|castellano)")
    english = (r"(?:(?:can|could|would) you )?(?:speak|talk|answer|respond|reply|switch|change)"
               r"(?: (?:the )?language)? (?:in |to )?(english|spanish)")
    match = re.fullmatch(spanish, value) or re.fullmatch(english, value)
    if match:
        return "en" if match[1] in ("ingles", "english") else "es"
    return None


def choose_language(text, previous="es", detected=None, probability=0.0):
    explicit = language_command(text)
    if explicit:
        return explicit
    value = normalized(text)
    words = re.findall(r"[a-z]+", value)
    spanish = set(("hola buenas gracias adios oye habla dime puedes podrias quiero necesito "
                   "que como cuando donde por favor abre busca cambia responde contesta "
                   "lista las los el una un estoy estas esto tengo eso para del "
                   "programacion diseno imprime revisa analiza inspecciona lee leeme escribe archivo "
                   "entiendes hablando hablar espanol ingles sistema ordenador estado proyectos agentes capacidades "
                   "buenos dias noches listo vale oyes").split())
    english = set(("hello hi hey thanks goodbye speak tell can could would want need what "
                   "how when where please open search change switch answer respond list "
                   "the this that these those my your you i am is are it for with from "
                   "about have explain inspect review implement fix debug read write file understand speaking "
                   "system information computer status projects agents capabilities morning evening good ready").split())
    scores = [len(set(words) & spanish), len(set(words) & english)]
    if max(scores) and scores[0] != scores[1]:
        return "es" if scores[0] > scores[1] else "en"
    # Shared words, names, numbers and a bare "okay" do not change the voice.
    if len(words) >= 2 and detected in ("es", "en"):
        threshold = .85 if len(words) == 2 else .65
        if isinstance(probability, (float, int)) and probability >= threshold:
            return detected
    return previous if previous in ("es", "en") else "es"


def localize(text, language):
    """Translate runtime-owned messages, leaving model prose and external names intact."""
    if language != "en":
        return text
    exact = {
        "Hola.": "Hello.", "Buenas.": "Hello.", "De nada.": "You're welcome.",
        "De acuerdo.": "Understood.",
        "Petición aceptada.": "Request accepted.",
        "Petición aceptada por el especialista.": "Request accepted by the specialist.",
        "No hay tareas activas.": "There are no active tasks.",
        "No hay proyectos registrados.": "There are no registered projects.",
        "¿En qué proyecto registrado?": "Which registered project?",
        "Modo gaming activado.": "Gaming mode enabled.",
        "Modo normal activado.": "Normal mode enabled.",
        "No he entendido la petición.": "I didn't understand the request.",
        "No he podido procesar la petición. Revisa el diagnóstico de voz.":
            "I couldn't process the request. Check the voice diagnostics.",
        "La misma tarea vuelve a la cola.": "The same task is back in the queue.",
        "Tarea cancelada.": "Task cancelled.",
        "La tarea ya terminó.": "The task has already finished.",
        "Tarea reanudada en la cola.": "Task resumed in the queue.",
        "Aprobación recibida. Continúo la misma tarea.": "Approval received. Continuing the same task.",
        "Necesito el nombre exacto de un proyecto registrado.": "I need the exact name of a registered project.",
        "Hay varias preguntas pendientes. Indica la tarea al responder.":
            "Several questions are pending. Specify the task when replying.",
        "No se ha ejecutado ninguna operación para esa petición.": "No operation was executed for that request.",
        "Falta conectar el proveedor del especialista.": "The specialist's provider is not connected.",
        "El especialista está definido, pero no tiene un proveedor de IA conectado.":
            "The specialist is defined, but its AI provider is not connected.",
        "No he podido resolver esa petición localmente. La interpretación por IA aún no está configurada.":
            "I couldn't resolve that request locally. AI interpretation is not configured.",
        "El instalador de actualizaciones aún no está conectado. No se ha cambiado ni reiniciado ARGOS.":
            "The update installer is not connected. ARGOS has not been changed or restarted.",
        "He solicitado cerrar la ventana. La aplicación puede pedir guardar cambios.":
            "I requested closing the window. The application may ask you to save changes.",
        "He solicitado abrir la ruta.": "I requested opening the path.",
        "El comando terminó correctamente.": "The command completed successfully.",
        "He enviado la página al navegador.": "I sent the page to the browser.",
        "El especialista ha devuelto una propuesta; no ha ejecutado cambios.":
            "The specialist returned a proposal; it did not make changes.",
        "La operación no pudo completarse. Comprueba el archivo, formato o herramienta requerida.":
            "The operation could not be completed. Check the required file, format or tool.",
    }
    if text in exact:
        return exact[text]
    patterns = (
        (r"Proyectos: (.*)", r"Projects: \1"),
        (r"(\d+) en ejecución, (\d+) en cola y (\d+) pendientes o bloqueadas\.",
         r"\1 running, \2 queued and \3 pending or blocked."),
        (r"He encontrado (\d+) aplicaciones\.", r"I found \1 applications."),
        (r"He solicitado abrir (.+)\.", r"I requested opening \1."),
        (r"Hay (\d+) ventanas abiertas\.", r"There are \1 open windows."),
        (r"(.+) está al frente\.", r"\1 is now in front."),
        (r"Hay (\d+) entradas visibles\.", r"There are \1 visible entries."),
        (r"He leído (.+)\.", r"I read \1."),
        (r"He guardado (.+)\.", r"I saved \1."),
        (r"El comando terminó con código (-?\d+)\.", r"The command exited with code \1."),
        (r"He encontrado (\d+) resultados\. El primero es (.+)\.", r"I found \1 results. The first is \2."),
        (r"Linux (.+)\. (\d+) CPU lógicas disponibles\.", r"Linux \1. \2 logical CPUs available."),
        (r"El STL contiene (\d+) triángulos\. Sus unidades no están declaradas\.",
         r"The STL contains \1 triangles. Its units are unspecified."),
        (r"He revisado el G-code: (\d+) movimientos lineales\. No se ha enviado a ninguna impresora\.",
         r"I inspected the G-code: \1 linear moves. It has not been sent to a printer."),
        (r"La operación (.+) está preparada y necesita tu aprobación\.",
         r"The \1 operation is prepared and needs your approval."),
        (r"Necesito aprobación para (.+)\.", r"I need approval for \1."),
    )
    for pattern, replacement in patterns:
        if re.fullmatch(pattern, text):
            return re.sub(pattern, replacement, text)
    if text.startswith("He inspeccionado "):
        return (text.replace("He inspeccionado ", "I inspected ")
                .replace("El repositorio tiene cambios.", "The repository has changes.")
                .replace("Sin cambios en archivos seguidos.", "No changes to tracked files.")
                .replace("No tiene un repositorio Git propio.", "It has no Git repository of its own."))
    if text.startswith("Puedo buscar en la web,"):
        return ("I can search the web, manage applications and windows, and work with files. "
                + ("Codex is configured for programming. " if "Codex" in text else "")
                + "Changes and commands require approval; the printer is not connected.")
    return text
