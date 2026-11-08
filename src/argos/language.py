"""Spanish/English turn selection. Short lexical evidence beats uncertain audio guesses."""
import re
import unicodedata


def normalized(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                           if not unicodedata.combining(c)).split()).strip(" .?!¿¡")


def voice_invocation(text):
    """Return the spoken request after a leading invocation, or None if absent.

    Whisper punctuation is not reliable. Restrict this to voice entry points;
    embedded, quoted and negated mentions remain untouched.
    """
    match = re.match(r"^[¿¡]?(?:hey[, ]+|oye[, ]+)?argos\b[\s,.:;!?¿¡-]*(.*)$", text.strip(), re.I)
    return match[1].strip() if match else None


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
                   "que como cuando donde cuanto cuanta cuantos cuantas cual cuales es por favor abre busca cambia responde contesta "
                   "lista las los el una un estoy estas esto tengo eso para del "
                   "programacion diseno imprime revisa analiza inspecciona lee leeme escribe archivo "
                   "entiendes hablando hablar espanol ingles sistema ordenador estado proyectos agentes capacidades "
                   "buenos dias noches listo vale oyes deja escuchar escucharme microfono").split())
    english = set(("hello hi hey thanks goodbye speak tell can could would want need what "
                   "how when where please open search change switch answer respond list "
                   "the this that these those my your you i am is are it for with from "
                   "about have explain inspect review implement fix debug read write file understand speaking "
                   "system information computer status projects agents capabilities morning evening good ready stop listening microphone").split())
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
        "NVIDIA tarda demasiado. Inténtalo de nuevo.": "NVIDIA is taking too long. Please try again.",
        "No he recibido una respuesta válida de NVIDIA a tiempo. Puedes volver a intentarlo.":
            "I couldn't get a valid response from NVIDIA. Please try again.",
        "NVIDIA no está respondiendo correctamente. Puedes volver a intentarlo.":
            "NVIDIA isn't responding correctly. Please try again.",
        "NVIDIA ha alcanzado su límite de uso. Inténtalo más tarde.":
            "NVIDIA's usage limit has been reached. Please try later.",
        "NVIDIA no acepta la credencial configurada.": "NVIDIA rejected the configured credential.",
        "NVIDIA no devolvió una respuesta completa. Puedes volver a intentarlo.":
            "NVIDIA didn't return a complete response. Please try again.",
        "NVIDIA excedió el tamaño máximo de respuesta.": "NVIDIA's response exceeded the size limit.",
        "NVIDIA no terminó la respuesta; no se reproducirá texto cortado.":
            "NVIDIA didn't finish its response. Please try again.",
        "NVIDIA devolvió una operación fuera del contrato de ARGOS.":
            "NVIDIA returned an unsupported operation. Nothing was executed.",
        "NVIDIA devolvió una decisión inválida; no se ha ejecutado ninguna acción.":
            "NVIDIA returned an invalid decision. Nothing was executed.",
        "NVIDIA devolvió una respuesta vacía.": "NVIDIA returned an empty response.",
        "Hola.": "Hello.", "Buenas.": "Hello.", "De nada.": "You're welcome.",
        "De acuerdo.": "Understood.",
        "Micrófono apagado.": "Microphone off.",
        "He solicitado abrir la lista de capacidades.": "I've requested the capabilities window.",
        "No pude abrir la lista de capacidades. El inventario sigue disponible por consola.":
            "I couldn't open the capabilities window. The inventory is still available through the console.",
        "He solicitado abrir el mapa de agentes.": "I requested opening the agent map.",
        "He solicitado abrir el monitor de tareas.": "I requested opening the task monitor.",
        "Petición aceptada.": "Request accepted.",
        "Petición aceptada por el especialista.": "Request accepted by the specialist.",
        "Prepararé el plan para que lo revises.": "I'll prepare the plan for your review.",
        "Plan confirmado. Continúo en segundo plano.": "Plan confirmed. Continuing in the background.",
        "No hay tareas activas.": "There are no active tasks.",
        "No hay proyectos registrados.": "There are no registered projects.",
        "No hay proyecto seleccionado.": "No project is selected.",
        "Selección de proyecto eliminada.": "Project selection cleared.",
        "Ficha del proyecto actualizada.": "Project profile updated.",
        "Ficha del proyecto consultada.": "Project profile retrieved.",
        "Alias del proyecto guardado.": "Project alias saved.",
        "Ese alias ya identifica otro proyecto.": "That alias already identifies another project.",
        "Ese nombre ya identifica otro proyecto.": "That name already identifies another project.",
        "El proyecto está fuera del ámbito de esta tarea.": "The project is outside this task's scope.",
        "¿En qué proyecto registrado?": "Which registered project?",
        "Selecciona una carpeta de proyecto concreta.": "Choose a specific project folder.",
        "Ese nombre o carpeta ya pertenece a otro proyecto.": "That name or folder already belongs to another project.",
        "La carpeta del proyecto no existe, no es accesible o contiene un enlace simbólico.":
            "The project folder does not exist, is inaccessible, or contains a symbolic link.",
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
        "He consultado los reproductores disponibles.": "I checked the available media players.",
        "Reproducción confirmada.": "Playback confirmed.",
        "Reproducción del vídeo confirmada.": "Video playback confirmed.",
        "Reproducción pausada.": "Playback paused.",
        "La extensión ARGOS de Firefox no está conectada. Cárgala desde about:debugging.":
            "The ARGOS Firefox extension is not connected. Load it from about:debugging.",
        "Firefox bloqueó el inicio. Permite audio y vídeo en la configuración de reproducción automática de YouTube.":
            "Firefox blocked autoplay. Allow audio and video in YouTube's autoplay permissions.",
        "No encontré un resultado cuyo título coincida con la canción y artista solicitados.":
            "I couldn't find a video title matching the requested song and artist.",
        "YouTube necesita atención en Firefox: puede haber un aviso de consentimiento o inicio de sesión.":
            "YouTube needs attention in Firefox: there may be a consent or sign-in screen.",
        "Firefox está atendiendo otra petición de ARGOS.":
            "Firefox is handling another ARGOS request.",
        "No pude confirmar que el vídeo solicitado empezase a reproducirse.":
            "I couldn't confirm that the requested video started playing.",
        "No se pudo completar la reproducción en Firefox.":
            "I couldn't start playback in Firefox.",
        "He inspeccionado el equipo. El inventario distingue observaciones y comprobaciones pendientes.":
            "I inspected the computer. The inventory distinguishes observations from pending checks.",
        "El especialista ha devuelto una propuesta; no ha ejecutado cambios.":
            "The specialist returned a proposal; it did not make changes.",
        "La operación no pudo completarse. Comprueba el archivo, formato o herramienta requerida.":
            "The operation could not be completed. Check the required file, format or tool.",
    }
    if text in exact:
        return exact[text]
    if re.match(r"Hay \d+ capacidades implementadas\.", text):
        return (re.sub(r"^Hay (\d+) capacidades implementadas\.", r"There are \1 implemented capabilities.", text)
                .replace("Ahora no están disponibles:", "Currently unavailable:")
                .replace("El inventario indica cuáles están comprobadas y cuáles dependen de la operación.",
                         "The inventory shows which prerequisites are verified and which depend on the operation.")
                .replace("Los cambios y comandos requieren aprobación.", "Changes and commands require approval."))
    patterns = (
        (r"Proyectos: (.*)", r"Projects: \1"),
        (r"Proyecto (.*) registrado\.", r"Project \1 registered."),
        (r"Proyecto (.*) seleccionado\.", r"Project \1 selected."),
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
