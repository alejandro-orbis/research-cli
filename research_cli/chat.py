"""Follow-up questions about a stored report."""

from .llm import ask_llm

MAX_CHAT_TURNS = 6  # how many previous Q&A pairs the model sees
EXIT_WORDS = {"exit", "quit", "salir"}


def build_chat_prompt(report: str, history: list[tuple[str, str]], question: str) -> str:
    """Prompt for a follow-up question, grounded only in the report."""
    turns = "\n".join(
        f"User: {q}\nAssistant: {a}" for q, a in history[-MAX_CHAT_TURNS:]
    )
    return (
        "You are answering follow-up questions about the research report below.\n"
        "- Answer ONLY with information from the report, keeping its [n] citations.\n"
        "- If the report doesn't cover the question, say so clearly and suggest "
        "running a new research on that topic.\n"
        "- Be concise. Answer in the same language as the user's question.\n\n"
        f"Report:\n{report}\n\n"
        + (f"Conversation so far:\n{turns}\n\n" if turns else "")
        + f"User: {question}\nAssistant:"
    )


def chat(client, row, ask=input) -> list[tuple[str, str]]:
    """Interactive Q&A about a stored report. `ask` is injectable for testing."""
    print(f"💬 Chatting about #{row['id']}: {row['question']}")
    print("   Ask a follow-up question, or type 'exit' to quit.\n")
    history: list[tuple[str, str]] = []
    while True:
        try:
            question = ask("> ").strip()
        except (EOFError, KeyboardInterrupt):  # Ctrl+D / Ctrl+C end the chat cleanly
            print()
            break
        if not question:
            continue
        if question.lower() in EXIT_WORDS:
            break
        answer = ask_llm(client, build_chat_prompt(row["report"], history, question))
        print(f"\n{answer}\n")
        history.append((question, answer))
    return history
