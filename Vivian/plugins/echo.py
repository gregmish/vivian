def register(register_plugin):
    def echo(*args):
        """Echoes back whatever you type"""
        return " ".join(args)
    register_plugin(
        "echo",
        echo,
        description="Echoes back arguments",
        tags=["test", "utility"],
        usage="!echo hello world"
    )