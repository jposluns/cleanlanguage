# Install Clean Language

These instructions cover ChatGPT, Claude, Gemini, and other AI systems. The public click-by-click version is also available at [cleanlanguage.ai/install](https://cleanlanguage.ai/install/).

Upgrading from a version before 1.0.11? The skill's internal name changed from `clean-language` to `cleanlanguage`, so uploading the new file adds a second skill beside the old one. Remove the old Clean Language skill first, then install the new file.

The site's [download link](https://cleanlanguage.ai/download) saves a version-named file such as `cleanlanguage-1.0.12.zip`, so repeat downloads stay distinguishable. The links below fetch the same current release under the stable name `cleanlanguage.zip`; either file installs identically.

## Claude

The preferred Claude method installs the complete Skill package.

1. Download [`cleanlanguage.zip`](https://github.com/jposluns/cleanlanguage/releases/latest/download/cleanlanguage.zip).
2. Do not unzip the file.
3. Open Claude in a desktop browser and sign in.
4. Open **Customize**, then **Skills**.
5. Click **+**.
6. Click **Create skill**, then **Upload a skill**.
7. Select `cleanlanguage.zip`.
8. Turn **Clean Language** on.

Test it in a new chat:

```text
Apply the Clean Language skill to this text: [paste your text]
```

Team and Enterprise administrators may need to enable Skills. An organization owner can upload the Skill once for everyone.

The matching checksum is available as [`cleanlanguage.zip.sha256`](https://github.com/jposluns/cleanlanguage/releases/latest/download/cleanlanguage.zip.sha256). For a plain-language walkthrough of checking it, see [cleanlanguage.ai/verify](https://cleanlanguage.ai/verify/).

### Claude Project fallback

Use this when Skills are unavailable.

1. Download the [portable Clean Language instructions](https://cleanlanguage.ai/downloads/cleanlanguage.md).
2. In Claude, click **Projects**, then **New Project**.
3. Name the project **Clean Language**.
4. Under **Project knowledge**, click **+** and upload the saved file.
5. Set the project instructions to:

```text
Use the Clean Language instructions in project knowledge for every response unless I explicitly tell you not to.
```

## ChatGPT

ChatGPT can use the same packaged Skill as Claude. Upload it once, and ChatGPT applies Clean Language when your request matches.

1. Download [`cleanlanguage.zip`](https://github.com/jposluns/cleanlanguage/releases/latest/download/cleanlanguage.zip). Do not unzip it.
2. Open ChatGPT.
3. In the left menu, click **Plugins**, then open **Skills**.
4. Click **Create**, then **Upload from your computer**.
5. Select `cleanlanguage.zip`.
6. Review the Skill, then install it.

Test it in a new chat:

```text
Apply the Clean Language skill to this text: [paste your text]
```

Workspace administrators may need to allow members to use and upload Skills.

### ChatGPT fallback: build the skill from the instructions file

Use this when your account cannot upload a skill.

1. Download the [portable Clean Language instructions](https://cleanlanguage.ai/downloads/cleanlanguage.md). It saves as `cleanlanguage.md`.
2. Open ChatGPT, click **Plugins**, then open **Skills**.
3. Click **Create**, then **Create with chat**.
4. Enter:

```text
Create a skill named Clean Language using the instructions in the file I am about to upload.
```

5. Attach `cleanlanguage.md` and send the message.
6. When ChatGPT shows the completed Skill, click **Install**.

When Plugins or Skills are unavailable, attach the instructions file to a normal chat and enter:

```text
Follow these writing rules for this conversation.
```

## Gemini

The easiest reusable Gemini method is a custom Gem.

1. Download the [portable Clean Language instructions](https://cleanlanguage.ai/downloads/cleanlanguage.md), then open the file and copy all of its text. It saves as `cleanlanguage.md`.
2. On a computer, open Gemini.
3. Open the menu on the left.
4. Click **Gems**. When necessary, click **Settings and help**, then **Gems**.
5. Click **New Gem**.
6. Name it **Clean Language**. For the description, you can use: `Applies the Clean Language writing standard so responses are precise, direct, and natural.`
7. Paste the copied `cleanlanguage.md` text into the **Instructions** box.
8. Set **no default tool**.
9. Click **Save**.

You can also add `cleanlanguage.md` as Gem knowledge: under **Knowledge**, click **Add files**, then **Upload files**, and select it. Pasting the instructions has given better responses than uploading alone, which Gemini sometimes ignores, so paste is the primary method. Using both together is an option.

After saving it, open **Gems** and select **Clean Language** whenever you need it. Gems created on the website can also appear in the Gemini mobile app.

## Copilot

Last verified 27 August 2026. The reusable method is a Copilot agent. Copilot caps an agent's instructions at 8000 characters, so paste the 8k file as the instructions and add the full standard as reference.

1. Download the [8k instructions](https://cleanlanguage.ai/downloads/cleanlanguage-8k.md). It saves as `cleanlanguage-8k.md`.
2. Open Microsoft 365 Copilot on a computer.
3. Open the agents panel and click **New agent**. Copilot offers to build the agent for you or to let you set it up yourself; click **Skip** to customize it yourself.
4. Name it Clean Language, and add a short description.
5. Open `cleanlanguage-8k.md`, copy all of it, and paste it into the **Instructions** box.
6. Find the option to add specific websites, and add `https://cleanlanguage.ai/downloads/cleanlanguage.md` as reference the agent can consult; the pasted instructions are what it follows.
7. Click **Create**, then select the Clean Language agent whenever you write.

No agent access? Attach `cleanlanguage.md` to a normal Copilot chat and say: `Follow these writing rules for this conversation.`

## Other AI systems

Clean Language works with local models, API-based assistants, and other systems that accept custom instructions, project knowledge, system prompts, or uploaded reference files.

1. Download the [portable Clean Language instructions](https://cleanlanguage.ai/downloads/cleanlanguage.md).
2. Save the file or copy its contents.
3. Add it to the AI tool as custom instructions, project knowledge, a system prompt, or an attached reference file.
4. Enter:

```text
Use the Clean Language instructions for every response unless I explicitly tell you not to.
```

## Technical installation

### Claude Code

```bash
mkdir -p .claude/skills
cp -R /path/to/cleanlanguage/cleanlanguage .claude/skills/cleanlanguage
```

### Gemini CLI

```bash
gemini skills install https://github.com/jposluns/cleanlanguage.git \
  --path cleanlanguage
```

Add `--scope workspace` for a project-specific installation. Verify discovery with:

```bash
gemini skills list
```

### ChatGPT package creation

```bash
python /path/to/skill-creator/scripts/package_skill.py ./cleanlanguage ./dist
```

The resulting archive must contain one `SKILL.md` entry point and retain its relative `references/` paths.

## Package contents and assurance

`cleanlanguage.zip` contains the `cleanlanguage/` directory with `SKILL.md`, the reference material, the agent configuration, the icons, and the licence and notice files. It contains no executable code and makes no network calls.
