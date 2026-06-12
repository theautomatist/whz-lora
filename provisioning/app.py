"""
app.py — FastAPI provisioning web app for whz-lora actuator provisioning.

Routes:
  GET  /healthz      — liveness probe (no auth, no ChirpStack call)
  GET  /             — single-device provisioning + CSV upload form
  POST /provision    — provision one device
  POST /import       — bulk CSV import
  GET  /dashboard    — device status overview
  POST /delete       — delete a device (requires confirmation field)

Optional HTTP Basic auth:
  Set PROVISIONING_AUTH_USER and PROVISIONING_AUTH_PASS to protect all routes
  except GET /healthz.  If either is unset or empty, the app runs open and
  emits a startup warning.
"""

import os
import secrets
import logging

import grpc
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import provisioning as prov
from validators import valid_eui, valid_appkey, parse_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional HTTP Basic auth
# ---------------------------------------------------------------------------

_AUTH_USER = os.environ.get("PROVISIONING_AUTH_USER", "")
_AUTH_PASS = os.environ.get("PROVISIONING_AUTH_PASS", "")
_AUTH_ENABLED = bool(_AUTH_USER and _AUTH_PASS)

_http_basic = HTTPBasic(auto_error=True)


def _require_auth(credentials: HTTPBasicCredentials = Depends(_http_basic)) -> None:
    """FastAPI dependency that enforces HTTP Basic auth (constant-time compare)."""
    user_ok = secrets.compare_digest(
        credentials.username.encode(), _AUTH_USER.encode()
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode(), _AUTH_PASS.encode()
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


# Build the dependency list once; empty list = open access.
_auth_dep = [Depends(_require_auth)] if _AUTH_ENABLED else []

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="whz-lora Provisioning")

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

templates = Jinja2Templates(directory=_TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Maximum CSV upload size (512 KB).
_MAX_CSV_BYTES = 512 * 1024


@app.on_event("startup")
def _startup_warning() -> None:
    if not _AUTH_ENABLED:
        logger.warning(
            "WARNING: provisioning app running WITHOUT authentication — "
            "set PROVISIONING_AUTH_USER/PROVISIONING_AUTH_PASS for any "
            "networked/VPN deployment."
        )


# ---------------------------------------------------------------------------
# Health (no auth — always open for container probes)
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, dependencies=_auth_dep)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# Provision single device
# ---------------------------------------------------------------------------


@app.post("/provision", response_class=HTMLResponse, dependencies=_auth_dep)
async def provision(
    request: Request,
    name: str = Form(...),
    dev_eui: str = Form(...),
    join_eui: str = Form(""),
    app_key: str = Form(...),
):
    errors = []
    norm_eui = None
    norm_join_eui = "0000000000000000"
    norm_key = None

    try:
        norm_eui = valid_eui(dev_eui)
    except ValueError as e:
        errors.append(str(e))

    if join_eui.strip():
        try:
            norm_join_eui = valid_eui(join_eui)
        except ValueError as e:
            errors.append(str(e))

    try:
        norm_key = valid_appkey(app_key)
    except ValueError as e:
        errors.append(str(e))

    if errors:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "error": "; ".join(errors),
                "dev_eui": dev_eui,
            },
        )

    try:
        status = prov.provision_device(
            dev_eui=norm_eui,
            name=name.strip() or norm_eui,
            join_eui=norm_join_eui,
            app_key=norm_key,
        )
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": True,
                "dev_eui": norm_eui,
                "device_name": name.strip() or norm_eui,
                "profile": prov.PROVISIONING_PROFILE,
                "status": status,
            },
        )
    except grpc.RpcError as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "dev_eui": norm_eui,
                "error": f"gRPC error ({e.code().name}): {e.details()}",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "dev_eui": norm_eui,
                "error": str(e),
            },
        )


# ---------------------------------------------------------------------------
# CSV bulk import
# ---------------------------------------------------------------------------


@app.post("/import", response_class=HTMLResponse, dependencies=_auth_dep)
async def csv_import(
    request: Request,
    csvfile: UploadFile = File(...),
):
    content = await csvfile.read()

    if len(content) > _MAX_CSV_BYTES:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "error": (
                    f"CSV file too large: {len(content)} bytes "
                    f"(limit is {_MAX_CSV_BYTES // 1024} KB)."
                ),
            },
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    parsed = parse_csv(text)
    row_results = []

    for entry in parsed:
        if not entry["ok"]:
            row_results.append(
                {
                    "label": str(entry.get("row", {})),
                    "status": "error",
                    "reason": entry["error"],
                }
            )
            continue

        d = entry["data"]
        label = f"{d['name']} ({d['dev_eui']})"
        try:
            status = prov.provision_device(
                dev_eui=d["dev_eui"],
                name=d["name"],
                join_eui=d["join_eui"],
                app_key=d["app_key"],
            )
            row_results.append({"label": label, "status": status, "reason": None})
        except grpc.RpcError as e:
            row_results.append(
                {
                    "label": label,
                    "status": "error",
                    "reason": f"gRPC error ({e.code().name}): {e.details()}",
                }
            )
        except Exception as e:
            row_results.append(
                {"label": label, "status": "error", "reason": str(e)}
            )

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "import_results": row_results,
        },
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/dashboard", response_class=HTMLResponse, dependencies=_auth_dep)
async def dashboard(request: Request):
    devices = []
    error = None
    try:
        devices = prov.list_device_states()
    except grpc.RpcError as e:
        error = f"gRPC error ({e.code().name}): {e.details()}"
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "devices": devices,
            "error": error,
            "application": prov.PROVISIONING_APPLICATION,
        },
    )


# ---------------------------------------------------------------------------
# Delete device
# ---------------------------------------------------------------------------


@app.post("/delete", response_class=HTMLResponse, dependencies=_auth_dep)
async def delete(
    request: Request,
    dev_eui: str = Form(...),
    confirm: str = Form(""),
):
    if confirm.strip().lower() != "delete":
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "dev_eui": dev_eui,
                "error": (
                    'Deletion not confirmed. '
                    'Type "delete" in the confirmation field.'
                ),
            },
        )

    try:
        norm_eui = valid_eui(dev_eui)
    except ValueError as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "dev_eui": dev_eui,
                "error": str(e),
            },
        )

    try:
        prov.delete_device(norm_eui)
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": True,
                "dev_eui": norm_eui,
                "deleted": True,
            },
        )
    except grpc.RpcError as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "dev_eui": norm_eui,
                "error": f"gRPC error ({e.code().name}): {e.details()}",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "success": False,
                "dev_eui": norm_eui,
                "error": str(e),
            },
        )


# ---------------------------------------------------------------------------
# Entry point (for local dev; production uses uvicorn in Dockerfile)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PROVISIONING_PORT", "8092"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
