TOOLS = {}


def register_tool(name: str, tool):
    TOOLS[name] = tool


def get_tool(name: str):
    return TOOLS.get(name)
