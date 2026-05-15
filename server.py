import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8000"))
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "enum-value-normalizer",
    "version": "1.0.0",
}
APP_NAME = "Enum Value Normalizer"
TOOL_NAME = "normalize_enum_value"
TOOL_TITLE = APP_NAME
TOOL_DESCRIPTION = (
    "Use this tool only when the user explicitly asks to normalize, map, or "
    "convert one raw enum-like value into one of a provided fixed list of "
    "allowed enum values. The user must explicitly provide both raw_value and "
    "allowed_values. Do not infer allowed_values. Do not create allowed_values. "
    "Do not use this tool to explain what enums are, teach programming "
    "concepts, classify urgency, make business decisions, interpret meaning, "
    "validate a full form, or answer general questions. If raw_value and "
    "allowed_values are not explicitly provided by the user, do not call this "
    "tool."
)
INPUT_SCHEMA = {
    "type": "object",
    "required": ["raw_value", "allowed_values"],
    "properties": {
        "raw_value": {
            "type": "string",
            "description": (
                "The exact free-text value explicitly provided by the user that "
                "needs to be normalized. Do not infer this value from a general "
                "question."
            ),
        },
        "allowed_values": {
            "type": "array",
            "description": (
                "The fixed enum values explicitly provided by the user and "
                "accepted by the downstream system. Do not infer, generate, "
                "expand, or guess allowed values."
            ),
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "normalized_value",
        "is_supported",
        "confidence",
        "status",
        "error",
    ],
    "properties": {
        "normalized_value": {"type": ["string", "null"]},
        "is_supported": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "status": {"type": "string", "enum": ["success", "error"]},
        "error": {
            "type": ["object", "null"],
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["code", "message"],
        },
    },
    "additionalProperties": False,
}
ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
TOOL_DEFINITION = {
    "name": TOOL_NAME,
    "title": TOOL_TITLE,
    "description": TOOL_DESCRIPTION,
    "inputSchema": INPUT_SCHEMA,
    "outputSchema": OUTPUT_SCHEMA,
    "annotations": ANNOTATIONS,
}


def load_html_file(filename):
    file_path = os.path.join(os.path.dirname(__file__), filename)
    with open(file_path, "r", encoding="utf-8") as html_file:
        return html_file.read()


def success_result(normalized_value, is_supported, confidence):
    return {
        "normalized_value": normalized_value,
        "is_supported": is_supported,
        "confidence": confidence,
        "status": "success",
        "error": None,
    }


def error_result(code, message):
    return {
        "normalized_value": None,
        "is_supported": False,
        "confidence": 0,
        "status": "error",
        "error": {
            "code": code,
            "message": message,
        },
    }


def tool_result_envelope(result):
    return {
        "structuredContent": result,
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, separators=(",", ":")),
            }
        ],
        "isError": result["status"] == "error",
    }


def canonicalize(value):
    lowered = value.strip().lower()
    collapsed = []
    for character in lowered:
        if character.isalnum():
            collapsed.append(character)
    return "".join(collapsed)


def normalize_enum_value(arguments):
    if not isinstance(arguments, dict):
        return error_result("invalid_value", "Tool arguments must be a JSON object.")

    extra_keys = set(arguments.keys()) - {"raw_value", "allowed_values"}
    if extra_keys:
        out_of_scope_keys = {"question", "prompt", "request", "task", "message", "text"}
        if extra_keys & out_of_scope_keys:
            return error_result(
                "out_of_scope",
                "This tool only normalizes an explicitly provided raw_value against explicitly provided allowed_values.",
            )
        return error_result(
            "invalid_value",
            "Only 'raw_value' and 'allowed_values' are accepted.",
        )

    if "raw_value" not in arguments:
        return error_result("missing_field", "The 'raw_value' field is required.")
    if "allowed_values" not in arguments:
        return error_result("missing_field", "The 'allowed_values' field is required.")

    raw_value = arguments["raw_value"]
    allowed_values = arguments["allowed_values"]

    if not isinstance(raw_value, str):
        return error_result("invalid_value", "The 'raw_value' field must be a string.")
    if not isinstance(allowed_values, list):
        return error_result("invalid_value", "The 'allowed_values' field must be an array.")
    if not allowed_values:
        return error_result(
            "invalid_value",
            "The 'allowed_values' field must contain at least one string value.",
        )
    if any(not isinstance(item, str) for item in allowed_values):
        return error_result(
            "invalid_value",
            "Every item in 'allowed_values' must be a string.",
        )

    normalized_raw = raw_value.strip().lower()
    out_of_scope_phrases = (
        "what is enum",
        "what does enum mean",
        "explain what enum means",
        "explain enum",
        "help me decide",
        "is this urgent",
        "classify urgency",
    )
    if normalized_raw in out_of_scope_phrases:
        return error_result(
            "out_of_scope",
            "This tool only normalizes an explicitly provided raw_value against explicitly provided allowed_values.",
        )

    if raw_value in allowed_values:
        return success_result(raw_value, True, 1)

    lowered_raw = raw_value.lower()
    for allowed_value in allowed_values:
        if lowered_raw == allowed_value.lower():
            return success_result(allowed_value, True, 1)

    canonical_raw = canonicalize(raw_value)
    for allowed_value in allowed_values:
        if canonical_raw == canonicalize(allowed_value):
            return success_result(allowed_value, True, 1)

    return success_result(None, False, 0)


def make_json_rpc_result(request_id, result):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def make_json_rpc_error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def handle_mcp_request(payload):
    if not isinstance(payload, dict):
        return make_json_rpc_error(None, -32600, "Invalid Request")

    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return make_json_rpc_error(request_id, -32600, "Invalid Request")

    method = payload.get("method")
    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return make_json_rpc_error(request_id, -32602, "Invalid params")

    if method == "initialize":
        return make_json_rpc_result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return make_json_rpc_result(request_id, {"tools": [TOOL_DEFINITION]})

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments")

        if tool_name != TOOL_NAME:
            return make_json_rpc_result(
                request_id,
                tool_result_envelope(
                    error_result(
                        "out_of_scope",
                        "This tool only normalizes an explicitly provided raw_value against explicitly provided allowed_values.",
                    )
                ),
            )

        try:
            result = normalize_enum_value(arguments)
        except Exception:
            result = error_result(
                "internal_error",
                "An unexpected server-side error occurred.",
            )
        return make_json_rpc_result(request_id, tool_result_envelope(result))

    return make_json_rpc_error(request_id, -32601, "Method not found")


class MCPRequestHandler(BaseHTTPRequestHandler):
    def _write_json(self, status_code, payload):
        response_bytes = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _write_html(self, status_code, html):
        response_bytes = html.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _write_text(self, status_code, text):
        response_bytes = text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _serve_html_file(self, filename):
        try:
            html = load_html_file(filename)
        except FileNotFoundError:
            self._write_json(404, {"error": "Not found"})
            return
        self._write_html(200, html)

    def do_GET(self):
        if self.path == "/":
            self._serve_html_file("index.html")
            return

        if self.path == "/privacy":
            self._serve_html_file("privacy.html")
            return

        if self.path == "/terms":
            self._serve_html_file("terms.html")
            return

        if self.path == "/support":
            self._serve_html_file("support.html")
            return

        if self.path == "/health":
            self._write_json(200, {"status": "ok", "app": APP_NAME})
            return

        if self.path == "/.well-known/openai-apps-challenge":
            self._write_text(200, os.getenv("OPENAI_APPS_CHALLENGE", ""))
            return

        self._write_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/mcp":
            self._write_json(404, {"error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_json(400, {"error": "Invalid Content-Length"})
            return

        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(400, make_json_rpc_error(None, -32700, "Parse error"))
            return

        response = handle_mcp_request(payload)
        self._write_json(200, response)

    def log_message(self, format, *args):
        return


def main():
    server = HTTPServer((HOST, PORT), MCPRequestHandler)
    print(f"Enum Value Normalizer MCP server listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
