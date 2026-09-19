$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
rtk docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" python:3.11-slim-bookworm python /workspace/docker/init_env.py
if ($LASTEXITCODE -ne 0) { throw '容器内配置初始化失败。' }
