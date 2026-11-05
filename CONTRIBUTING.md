# Flujo de trabajo y versiones

## Entornos

| Entorno | Rama | Dónde corre | `APP_ENV` | Gmail |
|---|---|---|---|---|
| **local** | cualquiera | tu máquina | `development` | dry-run (solo lectura) |
| **DEV** | `develop` | Railway, entorno `development` | `development` | dry-run |
| **PROD** | `main` | Railway, entorno `production` | `production` | real |

DEV y PROD usan **la misma imagen**; solo cambian las variables de entorno.

## Ramas

```
main      ← PROD. Siempre desplegable. Solo recibe merges de develop, hotfix/* y commits de datos.
develop   ← DEV. Integración de código nuevo.
feat/*    ← una funcionalidad. Sale de develop, vuelve a develop por PR.
fix/*     ← un bug no urgente. Igual que feat/*.
hotfix/*  ← bug urgente en PROD. Sale de main, va a develop y luego a main.
```

### Código nuevo
1. `git switch develop && git pull`
2. `git switch -c feat/descripcion-corta`
3. Commits pequeños (ver convención abajo).
4. `uv run ruff check . && uv run pytest`
5. PR `feat/...` → `develop`. CI debe estar en verde.
6. Probar en DEV (Railway, entorno `development`).
7. Release: PR `develop` → `main` (ver abajo).

### Hotfix (PROD roto o inseguro)
1. `git switch main && git pull && git switch -c hotfix/descripcion`
2. Arreglo mínimo + test.
3. Merge a `develop` (se valida en DEV) y luego a `main`.
4. Subir el PARCHE de la versión (`0.2.0` → `0.2.1`) y anotar en `CHANGELOG.md`.

### Commits de datos financieros
Los saldos y movimientos (`settings.json`, `claude_memory.md`, `finanzas/movimientos.csv`)
siguen yendo **directo a `main`** (ver `CLAUDE.md`). Para que `develop` no se quede atrás:

```bash
git switch develop && git merge main && git push
```

## Convención de commits (Conventional Commits)

```
<tipo>(<ámbito opcional>): <resumen en imperativo>

<por qué se hizo el cambio>
```

| Tipo | Uso |
|---|---|
| `feat` | funcionalidad nueva → sube MENOR |
| `fix` | corrección de bug → sube PARCHE |
| `refactor` | cambio interno sin cambiar comportamiento |
| `test` | solo tests |
| `docs` | solo documentación |
| `build` / `ci` | dependencias, empaquetado, pipeline |
| `chore(data)` | actualización de datos financieros |

## Versiones (SemVer)

`MAYOR.MENOR.PARCHE` en `pyproject.toml` y `gmailmcp/__init__.py` (un test verifica que coincidan).

- **PARCHE** (`0.2.0 → 0.2.1`): solo correcciones.
- **MENOR** (`0.2.x → 0.3.0`): funcionalidad nueva compatible.
- **MAYOR** (`0.x → 1.0.0`): cambio incompatible (por ejemplo, otro formato de `settings.json`).

### Publicar una versión
1. En `develop`: mover lo de `[Unreleased]` en `CHANGELOG.md` a la versión nueva y subir la versión en `pyproject.toml` y `gmailmcp/__init__.py`.
2. PR `develop` → `main`, merge.
3. Etiquetar: `git tag -a v0.3.0 -m "v0.3.0" && git push origin v0.3.0`.
4. Comprobar `https://<dominio-prod>/health` → `"version": "0.3.0"`.

### Rollback
Railway → servicio `web` → *Deployments* → redeploy del anterior. En git: `git revert <commit>` en una rama `hotfix/*`.

## Comandos útiles

```bash
uv sync                                     # entorno local (Python 3.11, igual que PROD)
uv run pytest                               # tests
uv run ruff check .                         # lint
uv run --env-file .env python dashboard.py  # dashboard local
uv run python -m gmailmcp.jobs cleanup      # un job a mano (labeler, financial_extractor, ...)
uv run python -m gmailmcp.jobs preview-summary
uv export --no-dev --no-hashes -o requirements.txt   # tras cambiar dependencias
```
