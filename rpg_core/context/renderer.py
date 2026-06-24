"""LLM-boundary renderer for structured RPG contexts."""

from __future__ import annotations

from rpg_core.context.rendering import render_jinja_template
from rpg_core.context.rpg_context import LayerType, Message, Role, RPGContext, UserExtensionBlock


class ContextRenderer:
    """Render structured context layers for the LLM request boundary."""

    def __init__(self, ctx: RPGContext) -> None:
        self._ctx = ctx

    def to_message_objects(self) -> list[Message]:
        msgs: list[Message] = []

        for type_ in (
            LayerType.FIXED,
            LayerType.PERSISTENT_MEMORY,
            LayerType.SUMMARY,
        ):
            content = self.render_layer(type_)
            if content:
                msgs.append(Message(role=Role.SYSTEM, content=content))

        msgs.extend(self._ctx.hot_history.messages)

        for type_ in (
            LayerType.STORY_MEMORY,
            LayerType.RECALLED_MEMORY,
            LayerType.STATUS_TABLES,
            LayerType.RP_MODULES,
        ):
            content = self.render_layer(type_)
            if content:
                msgs.append(Message(role=Role.SYSTEM, content=content))

        user_content = self.render_layer(LayerType.USER_MESSAGE)
        if user_content:
            msgs.append(Message(role=Role.USER, content=user_content))

        return msgs

    def render_layer(self, type_: str) -> str | None:
        if type_ == LayerType.FIXED and self._ctx.fixed_layer.active:
            return render_jinja_template(
                "layers/fixed_layer.jinja",
                fixed_sections=self._ctx.fixed_layer.sections,
                sections=self._ctx.fixed_layer.sections,
                world_name=self._ctx.fixed_layer.world_name,
                lorebook_entries=self._ctx.fixed_layer.lorebook_entries,
                characters=self._ctx.fixed_layer.characters,
            )
        if type_ == LayerType.PERSISTENT_MEMORY and self._ctx.persistent_memory.active:
            return render_jinja_template(
                "modules/persistent_memory.jinja",
                persistent_memory=self._ctx.persistent_memory.sections,
            )
        if type_ == LayerType.SUMMARY and self._ctx.summary.active:
            return render_jinja_template("modules/overall_summary.jinja", text=self._ctx.summary.text)
        if type_ == LayerType.STORY_MEMORY and self._ctx.story_memory.active:
            return render_jinja_template("modules/story_memory.jinja", story_details=self._ctx.story_memory.details)
        if type_ == LayerType.RECALLED_MEMORY and self._ctx.recalled_memory.active:
            return render_jinja_template("modules/recalled_memory.jinja", recalled_items=self._ctx.recalled_memory.items)
        if type_ == LayerType.STATUS_TABLES and self._ctx.status_tables.active:
            return render_jinja_template("modules/status_tables.jinja", status_tables=self._ctx.status_tables.tables)
        if type_ == LayerType.RP_MODULES and self._ctx.rp_modules.active:
            return render_jinja_template("modules/rp_modules.jinja", sections=self._ctx.rp_modules.sections)
        if type_ == LayerType.USER_MESSAGE and self._ctx.user_message.active:
            before = [self._render_user_extension(block) for block in self._ctx.user_message.before]
            after = [self._render_user_extension(block) for block in self._ctx.user_message.after]
            return render_jinja_template(
                "layers/user_message.jinja",
                user_before=[item for item in before if item],
                user_input=self._ctx.user_message.user_input,
                user_after=[item for item in after if item],
            )
        return None

    @staticmethod
    def _render_user_extension(block: UserExtensionBlock) -> str:
        try:
            return render_jinja_template(block.template, **block.data)
        except Exception:
            return ""
