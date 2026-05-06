"""Platform/external-dependency layer.

Anything that touches the OS (Win32 API), spawns processes, hits the network,
or loads heavy ML models lives here. The rest of the codebase imports from
`infra` only through the narrow public functions defined in each module.
"""
