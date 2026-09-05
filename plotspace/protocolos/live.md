<!-- JARVIS_LIVE_START -->
## 🔴 Swarm coordination — `.jarvis/jv`

You work with other agents on the SAME tree. Don't read state files to find out: ask when you need to.

    .jarvis/jv estado      what the others are touching and what arrived for you
    .jarvis/jv inbox       your new messages (do NOT read .jarvis/MAILBOX.md whole)
    .jarvis/jv msg "<agent>" "<text>"    leave a notice (does NOT interrupt)
    .jarvis/jv ask "<agent>" "<question>"  ask and WAIT for the answer
    .jarvis/jv claim "<symbol|file|folder>"  reserve YOUR zone
    .jarvis/jv commit -m "<message>"      commit only YOUR work, by hunk

The rules that matter:

1. **Claim your zone before starting**: `jv claim` on the functions, ids or files you're about to touch. Claim by NAME, never by line number (lines move). Whatever nobody claimed is granted on the spot; if you need more on the fly, claim it too.
2. **Never rewrite a whole file** that isn't yours (`Write` over something existing). Edit by zone: two agents in different zones of the same file coexist fine, but a full overwrite with your stale copy erases the other's work without a trace. Jarvis stops you if it happens.
3. **Don't delete or rename what another agent claimed.** Jarvis stops you before writing, naming the owner. If it really must go, leave them a `jv msg` and let them adapt it — yanking it out breaks their code without them knowing. (Using their function is fine; nobody stops you.)
4. **Commit with `jv commit`**: stages only your stuff, hunk by hunk. Bare `git add` sweeps in the other's uncommitted work that lives in the same file.
5. **`msg` leaves the notice; `ask` is what INTERRUPTS.** A `jv msg` lands in the other's inbox and they pick it up when they resume: it does NOT wake them (if they already closed their task, they keep resting). If you need a reaction NOW use `jv ask`, and if you're handing off work start the message with `HANDOFF` — those two do wake them. This exists because most messages landed on agents whose task was already closed, burning a whole turn for nothing. And the recipient is **another terminal, by its EXACT name**: writing to `@jarvis` or "the system" reaches NOBODY.
6. **A dead agent 💀 is not coming back.** If `jv estado` marks one like that, its territory is free and the guard won't block you on its files: don't ask its permission nor wait for it. And a **⚠ Inheritance** you see is someone's uncommitted work from an agent that left — nobody's coming for it: if you touch one of those files, commit it yourself with a message saying what it is.
7. **Commit before closing your task.** Real finished work left uncommitted in this tree is work another agent sweeps or inherits. What does NOT get committed: localhost trials, mockups, screenshots and build artifacts — those go to `.gitignore`, not to a commit.
8. **Your task is YOUR task — don't glom onto someone else's.** You verify YOUR work; theirs only if its owner asks you to or your task depends on it, and once. Acks (OK/thanks/received/"verified, all good") get NO reply: each message burns the other a whole turn. Cap: 2 of your messages per thread with the same agent on the same subject — after that decide alone with what you have, and if the disagreement matters leave it in a memory. The mailbox is not a chat: most of its traffic ends up being cross-checks and courtesy — one message per fact, and it's done, or it goes to a memory.
9. **Never wait for someone else's commit.** Intertwined uncommitted in the same file? `jv commit` stages ONLY your hunks (uses real provenance): commit NOW and continue. Asking «commit first and tell me» waits an average of an HOUR, when the tool solves it alone.

`.jarvis/LIVE.md` still exists (who owns what, permissions, reservations) if you want the detail, but `jv estado` gives you what you need.
<!-- JARVIS_LIVE_END -->
