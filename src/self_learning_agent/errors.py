class AgentError(Exception):
    """Base application error."""


class ConfigurationError(AgentError):
    pass


class ConversationNotFoundError(AgentError):
    pass


class ConversationFinalizedError(AgentError):
    pass


class MemoryNotFoundError(AgentError):
    pass
