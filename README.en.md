[简体中文](README.md) | **English**

# 大广赛学院奖 Skill · Daguangsai & Academy Award Skill

Let your AI agent automate the creative workflow from brief analysis to production, delivering competition work prepared to the brief's requirements.

Provide the brief, brand assets, and creative requirements. `student-ad-competition-copilot` directs the agent to analyze the brief, retrieve references, develop ideas, and use available tools to produce and revise the work. After content review and file checks, it delivers advertising images, final copy, or an editable marketing plan.

## What this skill can do

| Track | Main functions | Deliverables |
| --- | --- | --- |
| Print advertising | Brief analysis, creative concepts, visual design, artwork production, and review | Advertising images exported to the brief's specifications, with delivery records |
| Ad copy | Product and audience analysis, concept development, writing, revision, and claim and length checks | Editable copy drafts and a final plain-text version |
| Marketing plans | Research, strategy, campaign design, budget planning, and presentation production | An editable PPTX and the PDF or page images required by the brief |

Deliverables depend on the brief, available assets, and tool capabilities. The skill can also handle brief analysis, creative discussion, or revisions on their own. Its default scope ends at artwork delivery and does not include registration or platform uploads.

This skill is under active development, with plans to support more competition tracks in future releases. Follow me on Xiaohongshu for version updates and development progress.

## Why use this skill

The skill connects brief analysis, creative development, production, and file export into an automated workflow, keeping the agent working toward delivery of the finished work.

1. **Understand the brief:** identify the communication task, supported product facts, required assets, and output specifications.
2. **Develop ideas:** retrieve cases and methods, then propose directions suited to the brand.
3. **Produce the work:** use available image, document, and script tools to create artwork, copy, or a marketing plan.
4. **Keep revising:** apply your feedback, retain agreed directions, and continue unfinished work.
5. **Check and deliver:** combine content review with file checks, then export the deliverables for the selected track.

You supply the materials and approve key directions and the final work. The agent executes the steps in between. You can also ask for just one part, such as brief analysis, a copy sample, or revisions to an existing plan.

## Install

### 1. Download the skill

Open the [v0.2.14 download page](https://github.com/Yuzeskyare/student-ad-competition-copilot/releases/tag/v0.2.14) and download `student-ad-competition-copilot-v0.2.14.zip` from the release assets.

### 2. Ask your AI agent to install it

In an agent chat that can work with local files, attach the ZIP or provide its full file path, then send the request below. The agent can handle extraction and installation.

```text
Install the Daguangsai & Academy Award Skill (student-ad-competition-copilot).
Version: v0.2.14
Package: [attach the ZIP or provide its full local path]
Follow this agent's installation procedure and keep the complete skill package,
including all supporting files. Back up any existing version before updating.
Confirm that the skill is available and tell me how to start creating.
```

### Installation and use in common agents

Find your agent below. The links lead to official documentation or product pages.

| Your agent | How to install | How to start |
| --- | --- | --- |
| [WorkBuddy](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market) | Open **技能 → 添加技能 → 上传技能** (Skills → Add skill → Upload skill), select the ZIP, and enable it | Ask the agent to use this skill by name |
| [TRAE / TraeCode](https://docs.trae.cn/ide_skills) | Open **设置 → 技能与命令 → 创建** (Settings → Skills and Commands → Create), choose global or project scope, upload the complete ZIP, and confirm | Ask the agent to use this skill by name |
| [豆包工作版 · Doubao Work](https://www.doubao.com/work) | Provide the package path and installation request in a work chat. Ask the agent to confirm that the current version can install the complete skill package, then follow the supported procedure | Once installation is confirmed, request this skill by name and attach your brief |
| [千问办公 · QwenWork](https://docs.qwenwork.cn/features/skills) | Give the agent the package path and installation request, or upload the complete skill files through **扩展 → 技能 → 安装技能** (Extensions → Skills → Install Skill) | Request this skill by name in a chat and attach your brief |
| [百度搭子 · DuMate](https://cloud.baidu.com/discover/dumate-skill-extension.html) | On the **Skills** page, open **添加 → 安装技能** (Add → Install Skill) and upload the complete ZIP | Start a new task, request this skill by name, and attach your brief |
| [Kimi Work](https://www.kimi.com/help/kimi-work/overview) | Open **Work** mode in the Kimi desktop app, provide the package’s local path, and send the installation request above | Start a new task, request this skill by name, and attach your brief |
| [Codex](https://learn.chatgpt.com/docs/build-skills) | Give Codex the ZIP or local path and send the installation request above | Start a new chat and ask it to use this skill to analyze your brief |
| [Claude Code](https://code.claude.com/docs/en/skills) | Provide the local path and installation request, adding “Install as a personal skill” | Enter `/student-ad-competition-copilot` and attach the brief and creative requirements |
| [Cursor](https://cursor.com/docs/skills) | In Agent mode, provide the local path and installation request, adding “Install as a personal skill” | Start a new Agent chat and request this skill by name |

The custom skill import entry point in Doubao Work has not yet been verified; confirm client support before installing. Other installation menus may also change between versions; use the linked guide if you cannot find an option. Use an agent mode that can read materials, save files, and run scripts. See below for image and presentation requirements.

## Preparation

**Recommended setup:** To get more out of this skill and achieve better creative results, use **Codex** with **GPT 6.1 Sol** and set reasoning effort to **High or higher**.

### Provide the brief and assets

- **Competition brief:** the current official brief, attachments or links, and the requirements for your chosen track.
- **Brand assets:** available logos, product images, and any assets required by the brief.
- **Creative requirements:** your track, style preferences, and existing ideas. If you have no direction yet, ask the agent to propose one based on the brief.

### Do you need other skills?

**Install this skill first, then add tools as needed for your chosen work.** Use any image, presentation, PDF, or search features already available; there is no need to install them again.

| What you want to create | What else you need | If something is missing |
| --- | --- | --- |
| Ad copy | Usually no additional writing skill; web search when research is needed | Provide the brief and product information to begin analysis and writing |
| Print advertising | Image generation or editing tools, or sufficient prepared visual assets | Ask the agent to recommend a compatible image tool, or bring back images made in another tool to continue production |
| Marketing plans | Tools that produce editable PPTX files, preview pages, and export PDF or images as required | Ask the agent to check its presentation capabilities and recommend additional skills or tools only if needed |

Use image, presentation, and PDF features already available in Codex. In WorkBuddy, TRAE, Doubao Work, QwenWork, DuMate, Kimi Work, Claude Code, Cursor, and other agents, also start with their existing tools. Add tools according to whether the agent can actually produce the files your task requires.

You do not need to research a long list of plugins first. After installation, send this request with your brief:

```text
Use the student-ad-competition-copilot skill for the
[print advertising / ad copy / marketing plan] track.
Before starting, check that you can read the brief, produce the work,
and export the required files.
If your existing tools are sufficient, begin. If anything is missing,
explain the impact, recommend skills or tools compatible with this agent,
and tell me how to install or activate them.
```

If a selected tool requires payment, an account, or service activation, follow that tool's setup instructions. Those services are not included in this skill package.

## Track-specific guides

Use these requests to start a new project. Replace the bracketed text and attach your brief. For undecided requirements, ask for suggestions based on the brief.

### Print advertising | Creative concepts and visual production

**Required materials:** the brief, brand logos, and product images. Include any ideas or visual references you already have.

```text
Use the student-ad-competition-copilot skill.
I am entering the print advertising track in [competition] for [brand or brief].
The brief and brand assets are attached.
Start by analyzing the brief and proposing creative and visual directions.
After we agree on a direction, produce a draft, revise it from my feedback,
then check and export the artwork to the competition's specifications.
My preferred style is [describe it, or ask for suggestions based on the brief].
```

**Workflow:** the agent analyzes the brief and proposes directions, then produces and revises artwork after your confirmation. Content review and file checks precede export to the brief's specifications.

### Ad copy | Creative expression and writing

**Required materials:** the brief, product information, and copy requirements. Add any preferences for tone, length, or form.

```text
Use the student-ad-competition-copilot skill.
I am entering the ad copy track in [competition] for [brand or brief].
The brief is attached. Analyze the product, audience, and communication task,
then propose directions for the copy.
I want [copy format, or ask for suggestions] with a [preferred tone] voice.
Start with a short sample. Once the direction is agreed, complete the copy
and check product claims, length, and competition requirements.
```

**Workflow:** the agent proposes a direction, uses a sample to establish the voice, and completes and refines the copy. It exports a plain-text final version after content review and length checks.

### Marketing plans | Strategy and campaign development

**Required materials:** the brief and any research you already have, along with required budgets, page limits, and submission formats.

```text
Use the student-ad-competition-copilot skill.
I am entering the marketing plan track in [competition] for [brand or brief].
The brief is attached. Start with brief analysis and necessary research,
then develop the strategy, creative theme, campaign activities,
budget, measurement approach, and execution plan.
After we agree on the strategy and page direction, produce an editable PPTX
and export the PDF or page images required by the competition.
Existing research: [list attachments, or write "none yet"].
```

**Workflow:** the agent develops the research and strategy, organizes the campaign and presentation pages, applies your feedback, and checks budgets, references, and delivery files.

To continue an existing project, provide the latest files, feedback, and confirmed directions. When changing conversations or tools, include the saved task folder so the agent can recover the actual progress.

## Creative references included

The skill includes case analyses, creative methods, and common problem checks to help the agent find references relevant to the current brief.

| Reference | How it helps |
| --- | --- |
| Case analyses | Understand how a case responds to its brief and identify ideas worth learning from |
| Creative methods | Connect product features, audience needs, and forms of expression |
| Common problems and checks | Check whether an idea answers the brief, product claims have support, and a plan can be executed |

References include sources or analytical evidence for use in the current task. Original images and videos are not distributed with the skill. Use of case artwork and brand assets remains subject to their applicable rights and terms. Follow the current official brief for competition rules and output requirements.

## Author

**[Edward Z](https://github.com/Yuzeskyare)**

Xiaohongshu ID: **7230966199**

## Issues and suggestions

When reporting a problem, include the skill version, AI tool, steps taken, expected result, and observed behavior, together with relevant errors or screenshots. For feature suggestions, describe the use case and the problem you would like to address.

Share only the material needed to investigate the issue. Remove credentials, personal information, and work that should not be public.

## License and terms of use

Original skill instructions, documentation, knowledge content, and Python scripts that the project has the right to license are provided under **CC BY-SA 4.0 (Creative Commons Attribution-ShareAlike 4.0 International)**. See [LICENSE](LICENSE) for the full terms and [licensing scope and third-party content](LICENSING.md) for the scope.

The license permits copying, redistribution, and adaptation, including for commercial purposes. When sharing, provide appropriate attribution, link to the license, and indicate changes as required by its terms. Share adaptations under the same or a compatible license, and do not impose additional legal terms or technological measures that restrict the rights granted by the license.

Third-party works, brand assets, and quotations are not covered by the project's grant merely because they are included or linked. Outputs do not automatically fall under this license solely because the skill was used; any protected material copied or adapted in them remains subject to its applicable terms.

See [third-party notices](skills/student-ad-competition-copilot/THIRD_PARTY_NOTICES.md) for the source index and additional credits.
