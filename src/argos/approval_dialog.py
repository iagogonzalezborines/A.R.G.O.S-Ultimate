"""Local spoken review; short-lived challenges never grant general authority."""
import hashlib
import json
import secrets
import time

from .models import ArgosError, Response, Status

WORDS = ("luna", "pino", "cobre", "marte", "faro", "nube", "roble", "lago",
         "verde", "plata", "barco", "campo", "norte", "sur", "gato", "tigre")


class ApprovalDialog:
    def __init__(self):
        self.challenges = {}

    def review(self, core, session, reference=""):
        tasks = [t for t in core.store.tasks(session) if t["status"] == Status.WAITING_APPROVAL
                 and (not reference or t["id"].startswith(reference))]
        if len(tasks) != 1:
            raise ArgosError("Indica la tarea: debe haber exactamente una aprobación pendiente seleccionada.")
        task = tasks[0]
        pending = task["result"]["pending_operation"]
        code = " ".join(secrets.choice(WORDS) for _ in range(4))
        self.challenges[session] = {"task_id": task["id"], "fingerprint": pending["fingerprint"],
                                    "code": code, "expires": time.monotonic() + 120}
        args = pending["arguments"]
        review = pending.get("review", args)
        visible = {k: v for k, v in review.items() if k not in ("content", "expected_sha256")}
        if "content" in args:
            visible["content_characters"] = len(args["content"])
            visible["content_sha256"] = hashlib.sha256(args["content"].encode()).hexdigest()
        description = json.dumps(visible, ensure_ascii=False)
        english = core.language() == "en"
        speech = (f"Task {task['id'][:8]}. Operation {pending['capability']}. {description}. "
                  f"Review the prepared content in task details. To authorize this operation only, say: approve {code}. "
                  "The code expires in two minutes." if english else
                  f"Tarea {task['id'][:8]}. Operación {pending['capability']}. {description}. "
                  f"El contenido preparado está en el detalle de la tarea. Para autorizar solo esta operación, di: aprueba {code}. "
                  "El código caduca en dos minutos.")
        return Response(speech, "approval_review", task["id"],
                        data={"fingerprint": pending["fingerprint"], "expires_in_seconds": 120})

    def consume(self, core, session, code):
        challenge = self.challenges.get(session)
        if not challenge or challenge["expires"] < time.monotonic():
            self.challenges.pop(session, None)
            raise ArgosError("Revisa primero la aprobación para obtener un código vigente.")
        if not secrets.compare_digest(code, challenge["code"]):
            raise ArgosError("El código no coincide. No se ha aprobado nada.")
        self.challenges.pop(session, None)
        task = core.store.task(challenge["task_id"])
        pending = (task["result"] or {}).get("pending_operation", {})
        if (task["session"] != session or task["status"] != Status.WAITING_APPROVAL
                or pending.get("fingerprint") != challenge["fingerprint"]):
            raise ArgosError("La operación pendiente ha cambiado. Revísala de nuevo.")
        return {"method": "approve", "session": session, "task_id": task["id"],
                "fingerprint": challenge["fingerprint"]}
