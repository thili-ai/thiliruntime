"""The Refund Agent — the one worker in this drill that's genuinely new. Computes a refund
amount from its own MCP-backed price/tax facts; needs only the order id, nothing about whether
the return is eligible. See lesson 3.
"""
import a2a.helpers as h
import a2a.types as t
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from fastapi import FastAPI
from mcp.client import Client as MCPClient
from mcp.server.mcpserver import MCPServer
from thilimcp import build_server

RPC_URL = "/a2a/v1"


class RefundExecutor(AgentExecutor):
    """Deliberately has no concept of eligibility — an empty dependency list in lesson 2's graph,
    on purpose, so lesson 5 has something genuinely independent to run concurrently. Deciding
    what to *do* with the amount this agent reports belongs to a different step. See README."""

    def __init__(self, mcp_server: MCPServer):
        self._mcp_server = mcp_server

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = h.new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.submit()
        await updater.start_work()

        try:
            order_id = int(context.get_user_input().strip())
        except ValueError:
            reply = updater.new_agent_message([t.Part(text="order id must be a whole number")])
            await updater.failed(message=reply)
            return

        async with MCPClient(self._mcp_server) as mcp_client:
            items_result = await mcp_client.call_tool("get_order_items", {"order_id": order_id})
            if items_result.is_error:
                reply = updater.new_agent_message([t.Part(text=items_result.content[0].text)])
                await updater.failed(message=reply)
                return
            items = items_result.structured_content["result"]

        subtotal_cents = sum(item["price_cents"] * item["quantity"] for item in items)
        tax_cents = sum(
            item["price_cents"] * item["quantity"] * item["tax_rate_percent"] // 100 for item in items
        )
        total_cents = subtotal_cents + tax_cents
        reply_text = f"order {order_id}: subtotal={subtotal_cents}, tax={tax_cents}, refund_amount={total_cents}"
        reply = updater.new_agent_message([t.Part(text=reply_text)])
        await updater.complete(message=reply)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def build_refund_card(base_url: str) -> t.AgentCard:
    return t.AgentCard(
        name="refund-agent",
        description="Computes a refund amount from an order's price and tax.",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        supported_interfaces=[t.AgentInterface(url=f"{base_url}{RPC_URL}", protocol_binding="JSONRPC")],
        capabilities=t.AgentCapabilities(streaming=False),
        skills=[
            t.AgentSkill(id="compute_refund_amount", name="Compute refund amount",
                         description="order id -> amount", tags=["refunds"]),
        ],
    )


def build_refund_app(base_url: str = "http://127.0.0.1:8105", shop_db_path: str = "shop.db") -> FastAPI:
    """Build the Refund Agent's FastAPI app, over the same seeded shop `thilia2a`'s Order Agent
    uses — same database, same deterministic seed, no coordination needed beyond the file path."""
    mcp_server = build_server(shop_db_path, reseed=True)
    card = build_refund_card(base_url)
    handler = DefaultRequestHandler(
        agent_executor=RefundExecutor(mcp_server), task_store=InMemoryTaskStore(), agent_card=card,
    )
    app = FastAPI()
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    )
    return app
