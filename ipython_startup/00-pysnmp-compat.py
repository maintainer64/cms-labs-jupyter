"""Compatibility for the synchronous pysnmp API used by Lab5-1.

pysnmp 7 removed ``pysnmp.entity.rfc3413.oneliner.cmdgen``. The laboratory
only relies on ``CommandGenerator.getCmd``, ``CommunityData`` and
``UdpTransportTarget``. Keep that small API working while using the maintained
async implementation underneath.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import types
from dataclasses import dataclass
from typing import Any, Coroutine


try:
    from pysnmp.entity.rfc3413.oneliner import cmdgen as _legacy_cmdgen  # type: ignore[import-not-found]
except ModuleNotFoundError:
    import pysnmp.entity.rfc3413 as _rfc3413
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData as _CommunityData,
        ContextData as _ContextData,
        ObjectIdentity as _ObjectIdentity,
        ObjectType as _ObjectType,
        SnmpEngine as _SnmpEngine,
        UdpTransportTarget as _UdpTransportTarget,
        get_cmd as _get_cmd,
    )

    @dataclass(frozen=True)
    class CommunityData:
        community_name: str
        mpModel: int = 1

    @dataclass(frozen=True)
    class UdpTransportTarget:
        transport_addr: tuple[str, int]
        timeout: float = 1
        retries: int = 5

    def _run_sync(coroutine: Coroutine[Any, Any, Any]) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: list[Any] = []
        failure: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(coroutine))
            except BaseException as error:  # Re-raised in the notebook thread.
                failure.append(error)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if failure:
            raise failure[0]
        return result[0]

    class CommandGenerator:
        def getCmd(
            self,
            auth_data: CommunityData,
            transport_target: UdpTransportTarget,
            *object_ids: str,
            **options: Any,
        ) -> tuple[Any, Any, Any, Any]:
            async def request() -> tuple[Any, Any, Any, Any]:
                target = await _UdpTransportTarget.create(
                    transport_target.transport_addr,
                    timeout=transport_target.timeout,
                    retries=transport_target.retries,
                )
                return await _get_cmd(
                    _SnmpEngine(),
                    _CommunityData(
                        auth_data.community_name,
                        mpModel=auth_data.mpModel,
                    ),
                    target,
                    _ContextData(),
                    *(
                        _ObjectType(_ObjectIdentity(object_id))
                        for object_id in object_ids
                    ),
                    **options,
                )

            return _run_sync(request())

    _cmdgen = types.ModuleType("pysnmp.entity.rfc3413.oneliner.cmdgen")
    _cmdgen.CommandGenerator = CommandGenerator
    _cmdgen.CommunityData = CommunityData
    _cmdgen.UdpTransportTarget = UdpTransportTarget

    _oneliner = types.ModuleType("pysnmp.entity.rfc3413.oneliner")
    _oneliner.cmdgen = _cmdgen
    _rfc3413.oneliner = _oneliner
    sys.modules[_oneliner.__name__] = _oneliner
    sys.modules[_cmdgen.__name__] = _cmdgen
