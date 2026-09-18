# How to use Locol Content AI

Locol Content AI turns what you already know — your business, your expertise, your hobbies —
into Reddit posts written in your voice. You get there in four stages: you tell the
app about your business, it brainstorms **stories** worth telling; you pick one story
and turn it into a **project**, it brainstorms the individual **posts** that make up
that story; then it drafts each post and hands you an editor to finish it.

The app runs at `http://localhost:8501` — see [deploy-local.md](deploy-local.md) to
get it started, or [deploy-k8s.md](deploy-k8s.md) for a cluster deployment. The final
stage opens in a separate editor page; [content-editor-flow.md](content-editor-flow.md)
covers that in detail.

---

## Table of contents

- [1. Getting started](#1-getting-started)
- [2. Stage 1 (optional) — Find Your Voice](#2-stage-1-optional--find-your-voice)
- [3. Stage 2 — The Business Survey](#3-stage-2--the-business-survey)
- [4. Stage 2b — Brainstorming Reddit stories](#4-stage-2b--brainstorming-reddit-stories)
- [5. Stage 3 — The Project Survey](#5-stage-3--the-project-survey)
- [6. Stage 3b — Brainstorming the topics within your story](#6-stage-3b--brainstorming-the-topics-within-your-story)
- [7. Stage 3c — Generating the content](#7-stage-3c--generating-the-content)
- [8. Stage 4 — The Content Editor](#8-stage-4--the-content-editor)
- [9. Settings and tools](#9-settings-and-tools)
- [10. Quick reference](#10-quick-reference)

---

## 1. Getting started

The landing page greets you with **"Your story, told in your *voice.*"** and two tabs:
**🔐 Login** and **📝 Register**. Register once with a username and password, then log
in — everything you create is private to your account.

Once you are in, the home page shows **"Welcome back, *username*!"** followed by
**Your workflow** — four cards describing the stages:

| | Stage | Badge | Button |
|---|---|---|---|
| **STAGE 1** | Find Your Voice | *Optional* | **🎤 Try Find Your Voice** |
| **STAGE 2** | Business Survey | *Recommended start* | **📝 Start Business Survey** |
| **STAGE 3** | Campaign Projects | | **🎯 Open Campaign Projects** |
| **STAGE 4** | Content Editor | *Unlocks later* | *(no button)* |

Stage 4 has no button because it opens from inside a Campaign Project once you have
generated content for an idea. See [section 8](#8-stage-4--the-content-editor).

### The sidebar

The sidebar is your real navigation and stays with you everywhere:

- **🏠 Home** — back to the stage overview.
- **📝 Business Survey** — expands to the four survey pages, so you can jump straight
  to one.
- **📁 Campaign Projects** — lists your projects; each expands to show its **💡 ideas**.
  Two small buttons sit beside the heading: **➕** to add a new project and **🔄** to
  refresh the list.
- **⚙️ Settings and Tools** — **⚙️ Config Manager** and **🎤 Find your voice**.

> **Before you press any "Generate" button**, make sure an LLM is configured under
> **⚙️ Config Manager → 🤖 LLMs**. Every AI step in this guide depends on it.

---

## 2. Stage 1 (optional) — Find Your Voice

Skip this if you are in a hurry; you can come back to it any time.

A **voice** is a description of how someone writes, saved under a name. Pick one on a
campaign project and every draft for that project is written in that style instead of a
generic AI tone.

> **🔍 Analyze a Reddit account is unavailable.** This tool used to derive a voice from
> Google's index of your Reddit posts. Reddit now blocks the automated access it
> depended on, so the username field and **Analyze Voice** are disabled. Write your
> voice by hand instead — you know how you sound better than a search engine does.

1. Open **🎤 Find your voice** from the sidebar.
2. Under **✍️ Create a voice**, give it a **Voice Name** and write the **Voice Prompt** —
   instructions to the AI about how the writing should sound. The more specific, the less
   generic the drafts. Worth covering:
   - sentence length and structure — short and punchy, or long and layered?
   - tone — dry, earnest, sarcastic, warm, detached?
   - humour — none, dry wit, self-deprecating, absurd?
   - vocabulary — plain, technical, slangy? Any words you would never use?
   - punctuation habits — caps for emphasis, ellipses, emojis, exclamation marks?
   - anything it should **never** do (marketing language and exclamation marks are the
     usual offenders).
3. Press **💾 Create Voice**. It appears under **Saved Voices**, where you can **✏️ Edit**
   it, copy it with **📋 Save as New**, or **🗑 Delete** it.
4. Use it: open a campaign project, and pick it in the **🎤 Voice** dropdown beside
   **🚀 Generate Content** (see [Stage 3c](#7-stage-3c--generating-the-content)).

Keep a few voices around — one for how you write, one for a more formal register — and
switch between them per project.

---

## 3. Stage 2 — The Business Survey

This is where most people start. The Business Survey is the foundation for
*everything* the AI writes for you, and you only fill it in once.

Open **📝 Business Survey** from the sidebar. The page is titled
**🚀 Business Content Discovery Tool** and runs across four pages.

### Working through the pages

A **Survey Progress: N of 4** line and progress bar sit at the top. At the bottom of
each page you get:

- **💾 Save Page** — saves your answers so far without moving on. Use it liberally.
- **⬅️ Previous** / **Next ➡️** — move between pages. **Next ➡️** checks the required
  fields first and refuses to advance until they are filled, naming the ones still
  blank: *"Please answer these required questions before proceeding: …"*

Required questions are marked with a **\*** next to the question, and a line under each
page heading tells you which way that page runs — either *"Questions marked \* are
required — everything else is optional"* or *"All questions on this page are optional"*.
- **💾 Save Business Survey** — replaces **Next ➡️** on the last page and completes
  the survey.

> **You get one business survey per account.** Saving replaces whatever was there
> before rather than adding a second one. Coming back later reloads your answers so
> you can edit and re-save them.

### Page 1 — 🏢 Basic Business Information

*"Let's start with the fundamentals about your business."*

| Question | Required |
|---|---|
| What is your business name? | ✅ |
| What does your business do? | ✅ |
| What industry are you in? — a dropdown of 15 industries (SaaS/Technology, Healthcare, Manufacturing, Consulting, E-commerce, Finance, Education, Real Estate, Marketing/Advertising, Legal Services, Food & Beverage, Retail, Construction, Non-profit, Other) | ✅ |
| Please specify your industry — appears only if you chose *Other* | |
| Who is your target audience? — demographics, job titles, company sizes, pain points | ✅ |
| What are your main products or services? — list 3–5 | |
| What makes you different from competitors? | |

### Page 2 — 🎯 Goals & Strategy

| Question | Required |
|---|---|
| What are your primary business goals? — pick any of Brand Awareness, Lead Generation, Thought Leadership, Customer Retention, Sales Growth, Market Education, Community Building, Product Launches, Recruitment, Investor Relations | ✅ |
| What topics does your audience care about most? | |
| What type of content performs best for you currently? | |
| Who are your main competitors? | |
| What industry publications, influencers, or thought leaders does your audience follow? | |

The goals you tick here come back later — each generated post idea is tagged with the
business goal it serves.

### Page 3 — 💡 Skills & Expertise

Nothing on this page is required.

| Question | Required |
|---|---|
| What are your primary areas of professional expertise? | |
| How many years of experience do you have in your field? — a range from *Less than 1 year* to *20+ years* | |
| What technical skills, tools, or methodologies do you use regularly? | |
| What credentials, certifications, or training do you hold? | |
| What specific problems have you solved that your customers typically struggle with? | |
| Do you have a unique process, framework, or methodology you use? | |
| What common mistakes do you see others in your industry make? | |

### Page 4 — 🎨 Hobbies & Interests

Nothing on this page is required either.

| Question | Required |
|---|---|
| What are your personal hobbies or interests outside of work? | |
| What sports, fitness, or outdoor activities do you enjoy? | |
| Do you have any creative hobbies? | |
| What topics do you love learning about in your personal time? | |
| Are you part of any hobby communities, clubs, or groups? | |
| Have any of your hobbies influenced how you run your business or think about your work? | |
| Which of your hobbies or interests do you think your target audience would relate to? | |

> **Why does it ask about hobbies?** Because Reddit rewards people, not brands. Pages
> 3 and 4 — your expertise and your interests — are the two pages the story brainstorm
> actually reads, along with your business name, industry and audience. Everything
> else shapes the posts later. One-line answers on these two pages produce generic
> stories; specific ones ("I restore vintage bicycles", "I've made every mistake in
> the book migrating legacy CRMs") produce stories worth reading. Nothing on either
> page is required, so you *can* click straight through — but these are the two pages
> worth slowing down for, and skipping them is what makes the brainstorm bland.

---

## 4. Stage 2b — Brainstorming Reddit stories

**Where to find it:** the bottom of the **fourth** survey page — 🎨 Hobbies &
Interests — and nowhere else. Scroll past the navigation buttons to the section headed
**📖 Generate Story Ideas**:

> *Use your skills and hobbies to generate personal story ideas for your target audience.*

Press **✨ Generate Story Ideas**. The AI reads your business identity plus your
Skills and Hobbies answers and comes back with **three to five story ideas**.

### What a story idea contains

Each idea appears as an expandable **📖 *Story title*** panel:

- **Angle** — how to frame the story as a personal narrative rather than a pitch.
- **Why relevant** — why your target audience will care about it.
- **Reddit post topics** — three topics that break the story into a series, each with
  a note on how it relates to the story and a list of **suggested subreddits**.
- **Emotion** — whether the story is meant to Inspire, Educate or Entertain.
- **Source** — whether it came from one of your skills or one of your hobbies.

### Two things to know before you press the button again

1. **Regenerating replaces everything.** Pressing **✨ Generate Story Ideas** a second
   time discards the whole previous set. If a story is worth keeping, turn it into a
   project first (below). Your saved ideas reload automatically the next time you open
   the page, so you do not need to regenerate just to see them.

2. **The "Reddit post topics" are suggestions, not selections.** They exist to show
   you what a series built on this story could look like — they are read-only, you
   cannot tick or edit them, and they do **not** carry into the project you create.
   The actual list of posts is generated separately in
   [Stage 3b](#6-stage-3b--brainstorming-the-topics-within-your-story), from the
   project survey. Read them as a preview of the shape of the series, then let them go.

### Picking a story

Press **🚀 Create Project** inside a story's panel. That creates a Campaign Project
named after the story, using the **Generated Story** question set, pre-filled with:

- a summary of your business survey answers, and
- the story's angle and why-relevant text as the skill content for the project.

You will see *"✅ Project '…' created! Open the Projects page to continue."* The
project now appears under **📁 Campaign Projects** in the sidebar.

You can create projects from several stories — one story, one project.

**🗑️ Clear Story Ideas** just hides the list from the page; it does not delete
anything, and the ideas come back when you return.

---

## 5. Stage 3 — The Project Survey

A **Campaign Project** is one story being turned into a series of posts. Each project
has its own survey, its own ideas, and its own drafts.

### Two ways to create one

- **From a story** — the **🚀 Create Project** button in Stage 2b. The project arrives
  pre-filled; you just review it.
- **From scratch** — press **➕** beside **📁 Campaign Projects** in the sidebar. The
  **➕ Create New Project** panel asks for a **Project Name:** and a **Question Set:**,
  then **Create Project** (or **Cancel**).

### Choosing a question set

The question set decides which questions the project survey asks you. **It is fixed
when the project is created** — pick deliberately.

| Question set | What it asks | Use it when |
|---|---|---|
| **Generated Story** | One page, **📝 Generated Story**, with two large fields: **Business Survey Summary** and *"What is the skill content that we are addressing in this project"* | The project came from **🚀 Create Project**. Both fields arrive filled in — read them, sharpen them, add anything the survey missed. |
| **Tell your story** | One page, **📖 Business Story**, eight questions: how you started the business, who your audience is and why, the moment you decided it was worth pursuing, why nobody had solved it well before, the challenges you solve (as a detailed list), what surprised you talking to users, *"Are there specific ideas you would like separate posts to cover?"*, and which channels to use | You already have the narrative in your head and want to write it out directly. The "specific ideas" question is powerful — each idea you list becomes its own post, so write one paragraph per idea with the title as the first sentence. |
| **Default Question Set** | Five pages, nineteen questions: **💝 Emotional Connection & Motivation**, **🎯 Untapped Angles & Positioning**, **👥 Audience Insights & Expansion**, **⏰ Cultural Moments & Timing**, **✨ Unique Differentiators** | You want a full strategic pass on a campaign rather than a single story. |

### Working through it

The mechanics mirror the Business Survey: a **Strategic Discovery Progress: N of M**
bar, **💾 Save Page**, and **⬅️ Previous** / **Next ➡️**. On the last page,
**Next ➡️** is replaced by **🎯 Complete Discovery & Generate Insights**, which saves
your answers and takes you to the insights page described next.

Required and optional questions work exactly as they do in the Business Survey:
required ones carry a **\***, and a line under each page heading says which way that
page runs. As shipped, none of the three question sets marks anything required — every
page reads *"All questions on this page are optional"* and nothing blocks **Next ➡️**.
Answer as much as you can anyway; the strategic insights and the brainstorm are only
as good as what you put in.

Selecting a project in the sidebar later reopens it with its own answers intact.

---

## 6. Stage 3b — Brainstorming the topics within your story

You land on the insights page after **🎯 Complete Discovery & Generate Insights**, and
whenever you reopen a project whose survey is already done.

### Reviewing your answers

The page opens with a **🎯 Project Survey** section and an **✏️ Edit Project Survey**
button that takes you back into the questions. Below it, one tab per survey category
groups your answers; expanding a question shows **Your Response:** alongside
**Potential Campaign Angles:** — quick suggestions generated locally from your answer
to help you spot what you have not said yet. These are prompts for your own thinking,
not AI output.

### Generating the posts

Under the tabs:

> *Send your strategic insights to the AI brainstorm engine for campaign development
> recommendations.*

Press **🚀 Generate Strategic Campaigns**. The AI reads both surveys — your business
survey *and* this project's answers — and returns the list of posts that make up your
series, under the heading **🎯 Project Post Ideas**.

**The first idea is always an introduction to the series.** That is deliberate: it
sets up the story so the posts that follow have context.

Each idea carries five fields:

| Field | What it is |
|---|---|
| **Title** | The post's working headline |
| **Description** | What the post covers and how it should be approached |
| **Content Type** | The kind of Reddit post — text post, link post, discussion, AMA, how-to, story… |
| **Platform** | Reddit |
| **Goal** | Which of your business goals from the survey this post serves |

### Working with the ideas

Every idea is a card with a **View Details** panel and these controls:

- **✏️ Edit** — opens **✏️ Edit Idea**, where all five fields are editable, with
  **💾 Save Changes**, **❌ Cancel** and **🗑️ Delete**. You must save or cancel before
  navigating away — the app will stop you with
  *"⚠️ Please save or cancel your idea edits before navigating."*
- **🧠 Brainstorm Content Snippet** — inside the edit panel. Type a free-form
  **Brainstorming Prompt** (for example *"Suggest 5 headline variations for this
  campaign idea"*) and the AI answers in the context of that specific idea. Every
  answer is kept under **Previous Content Snippets** with its prompt and timestamp, so
  you can try several angles and compare. A **🎤 Voice** dropdown sits above the button —
  it is the same project-wide selection used by **🚀 Generate Content**, so changing it
  here changes it there too.
- **➕ Add Campaign Idea Manually** — a form (Title, Description, Content Type,
  Platform, Goal) for a post the AI missed. It joins the list as an equal.
- **🗑️ Clear Strategic Response** — deletes every idea in this project. Unlike
  **🗑️ Clear Story Ideas** in Stage 2b, this one really removes them.

Refine the list until it reads like a series you would actually want to publish, then
move on.

---

## 7. Stage 3c — Generating the content

Each idea card has a **Generate Content** checkbox. Tick the ideas you want drafted —
a running count appears at the bottom, *"✅ N idea(s) selected for content
generation"* — then press **🚀 Generate Content** under **🚀 Content Generation**.

Above the button sits a **🎤 Voice** dropdown listing every voice you saved in
[Stage 1](#2-stage-1-optional--find-your-voice), plus **— No voice —**. Whatever you
pick is written into the AI's instructions for every draft in the batch, so they come
out in that style rather than the house default. The choice is remembered against the
project: it survives a reload and applies to the brainstorm panel too. Leave it on
**— No voice —** for the neutral tone.

Some notes:

- Each selected idea is written separately, so a batch of ten takes roughly ten times
  as long as one. Start with one or two to see whether the output is what you expected.
- **A maximum of 25 ideas can be generated in one batch.** Select fewer and run it
  twice if you have more.
- The prompt template used is chosen by the idea's **Platform**.
- A voice changes *how* a draft reads, not what it is about or its format — the platform's
  prompt template still decides that.

When it finishes, each card gains a **🤖 Generated Content** section with the draft,
a note of which template was used, and a timestamp. If a draft failed you get
**⚠️ Generation Error** with the reason instead — fix the cause and generate that idea
again.

Two more buttons close out the section: **🔄 Refresh Content** re-reads the drafts
(useful after editing in the Content Editor) and **🗑️ Clear Selection** unticks
everything.

---

## 8. Stage 4 — The Content Editor

Once an idea has generated content, a **📝 Content Editor** button appears on its card.
That is what *"Unlocks later"* on the Stage 4 home card means — the editor has nothing
to open until a draft exists.

The button opens the editor in a new page, already loaded with that draft. It gives
you a **Content Editor** pane for the text itself, plus **Prompt Input**, **History**
and **Prompt Editor** panes. **Submit Prompt** re-prompts the AI to rework the draft;
**Save Content** saves what you have. Saved work flows back to the idea card in the
project, so **🔄 Refresh Content** will show your edited version.

The editor is documented in full in
[content-editor-flow.md](content-editor-flow.md).

There is no publishing step — you copy the finished post to Reddit yourself.

---

## 9. Settings and tools

**⚙️ Settings and Tools → ⚙️ Config Manager** opens the **⚙️ Configuration Manager**
with three tabs:

- **🤖 LLMs** — the models available to the app and their API keys (masked after the
  first save). **At least one must be configured before any Generate button works.**
- **📺 Channels** — the platforms content can be written for.
- **📝 Prompts** — the prompt templates used when drafting content. Each template is
  tagged with the platform it applies to, which is how Stage 3c picks one.

**🎤 Find your voice** is the same tool as [Stage 1](#2-stage-1-optional--find-your-voice),
reachable at any time — create, edit and delete the voice profiles your projects write in.
(Its Reddit analyzer is disabled; Reddit blocks the access it needed.)

---

## 10. Quick reference

| Stage | Where | What you press | What you get |
|---|---|---|---|
| 1 | 🎤 Find your voice | write a Voice Prompt → **💾 Create Voice** | A reusable writing-style profile to pick per project |
| 2 | 📝 Business Survey, pages 1–4 | **Next ➡️** → **💾 Save Business Survey** | Your business, expertise and interests on file (one per account) |
| 2b | Bottom of survey page 4 | **✨ Generate Story Ideas** | 3–5 stories, each with an angle, a reason it lands, and three suggested post topics |
| — | A story panel | **🚀 Create Project** | A Campaign Project pre-filled from that story |
| 3 | 📁 Campaign Projects | **🎯 Complete Discovery & Generate Insights** | The project survey answered and saved |
| 3b | Project insights page | **🚀 Generate Strategic Campaigns** | **🎯 Project Post Ideas** — the actual posts in your series |
| 3c | Idea cards | tick **Generate Content** → pick a **🎤 Voice** → **🚀 Generate Content** | A draft on each selected card (25 per batch), in the chosen voice |
| 4 | An idea with a draft | **📝 Content Editor** | The full editor, with re-prompting and save |
