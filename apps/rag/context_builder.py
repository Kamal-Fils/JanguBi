from typing import Dict


class ContextBuilder:
    """
    Takes the raw context string outputs from the engines and formats them 
    into a structured template for the final Gemini Prompt.
    """

    @staticmethod
    def build(contexts: Dict[str, str]) -> str:
        final_context = []

        bible_ctx = contexts.get("bible")
        if bible_ctx:
            final_context.append("=== PASSAGES BIBLIQUES ===")
            final_context.append(bible_ctx)
            final_context.append("")
        
        rosary_ctx = contexts.get("rosary")
        if rosary_ctx:
            final_context.append("=== ROSAIRE ===")
            final_context.append(rosary_ctx)
            final_context.append("")

        if not final_context:
            return ""  # aucun contexte -> le service renvoie le message d'absence

        return "\n".join(final_context)
