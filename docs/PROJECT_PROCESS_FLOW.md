# Project Process Flow

This document explains what will happen when a user uploads a video and how the
system will produce a final answer.

The main idea is simple:

We are not only chunking a video. We are converting the video into a
timeline-aware memory system.

## 1. Video Upload

The user uploads a video from the frontend.

The backend receives it and creates a unique `video_id`.

Example:

```text
video_20260722_000001
```

The video is saved in:

```text
data/uploads/
```

Then the backend creates a media manifest.

The manifest stores:

```text
video path
duration
fps
resolution
codec
audio path
processing status
pipeline version
```

This manifest becomes the source of truth for the whole pipeline.

## 2. Audio Extraction

The system extracts audio from the uploaded video using FFmpeg or an equivalent
media tool.

Output:

```text
data/processed/audio/{video_id}.wav
```

Why this matters:

The audio is needed for transcription. Most useful answers come from combining
what was said with what appeared visually.

## 3. Speech Transcription

The extracted audio is sent to Faster-Whisper.

It creates:

```text
full transcript
segment timestamps
word-level timestamps if available
speaker/confidence metadata
```

Example:

```json
{
  "text": "He compares cats and dogs using this graph",
  "start_seconds": 9676.2,
  "end_seconds": 9682.4
}
```

This lets the system answer questions like:

```text
"What did he say at 2:41:16?"
```

## 4. Timeline Chunking

This is the most important base improvement.

Instead of depending only on scene detection, we create one reliable canonical
timeline.

Example:

```text
atom_000001: 00:00.000-00:07.200
atom_000002: 00:07.200-00:14.800
atom_000003: 00:14.800-00:23.100
```

Atomic spans do not overlap. Retrieval adds previous and next atoms dynamically
when a question needs more context, avoiding duplicate evidence in storage.

Each atom stores:

```text
start time
end time
previous chunk
next chunk
transcript inside that time
related frames
related clip
event id
chapter id
```

This means the system can answer from any timeline, even if there was no clean
visual scene cut.

## 5. Frame And Clip Extraction

For every chunk, we extract:

```text
keyframes
short video clip
```

Frames help with simple visual understanding.

Clips are needed later for advanced Video-Language Models like:

```text
Qwen2.5-VL
Video-LLaMA
LLaVA-Video
```

Why clips matter:

A single frame can say:

```text
"There is a graph."
```

A clip can say:

```text
"He draws the graph, points to the curve, and explains why cats and dogs differ."
```

That is much more powerful.

## 6. OCR And Visual Understanding

The system extracts visible text from frames or clips.

Example:

```text
Cats vs Dogs
Feature Comparison
Blue Graph
```

Then the visual model creates structured visual metadata:

```text
objects
actions
interactions
visual summary
motion summary
on-screen text
```

Example:

```json
{
  "objects": ["blue graph", "slide", "table"],
  "actions": ["draws graph", "points to axis"],
  "summary": "The lecturer compares cats and dogs using a blue graph."
}
```

This is what enables vague memory search.

## 7. Semantic Event Grouping

Atomic chunks are small, but users usually think in events.

So we group nearby chunks into semantic events.

Example:

```text
Event 10:
02:40:52 - 02:43:22
"The lecturer compares cats and dogs using a blue graph."
```

This event may contain multiple chunks.

Why this matters:

If the exact visual clue appears at `02:41:16`, the explanation may start at
`02:40:52` and continue until `02:43:22`.

So we retrieve the whole event, not just one tiny moment.

## 8. Chapter Grouping

Events are grouped into larger chapters.

Example:

```text
Chapter 3:
"Feature Comparison Examples"
02:30:00 - 02:55:00
```

This helps with broad questions like:

```text
"Summarize the part where he explains feature comparison."
```

## 9. World Memory Creation

This is the future-ready part.

Instead of only storing captions, we store memory-like structures:

```text
entities
actions
relationships
temporal evolution
repeated concepts
```

Example:

```text
blue graph appears at 02:41:16
same concept returns at 02:58:40
final summary appears at 03:04:12
```

This lets the AI connect different parts of the video.

So when user asks:

```text
"Where does he return to the same idea later?"
```

The system can follow the timeline.

## 10. ChromaDB Indexing

Now we store the processed information into ChromaDB.

But not in just one collection.

We use multiple collections:

```text
video_chunks_text
video_chunks_audio
video_chunks_visual
video_events
video_entities
video_world_memory
```

Each collection has a different job.

Text collection:

```text
finds concepts from transcript
```

Audio collection:

```text
finds spoken phrases
```

Visual collection:

```text
finds visual memories like blue graph, table, diagram
```

Events collection:

```text
finds larger explanation sections
```

Entities collection:

```text
connects repeated objects/topics across the timeline
```

World memory collection:

```text
connects long-range ideas
```

## 11. User Asks A Question

Now suppose the user asks:

```text
"I remember he drew a blue graph but forgot why."
```

The query first goes to a Planner Agent.

The planner decides:

```text
This is a vague visual memory query.
Search visual chunks.
Search entities.
Search events.
Fetch nearby transcript.
Use temporal reasoning.
```

## 12. Retrieval

The Retriever searches multiple ChromaDB collections.

It may find:

```text
chunk at 02:41:16
event from 02:40:52 to 02:43:22
entity: blue graph
related later moment at 02:58:40
```

It also fetches:

```text
previous chunk
next chunk
parent event
parent chapter
```

This is how the system understands context.

## 13. Evidence Verification

The Evidence Verifier checks:

```text
Does the visual evidence actually mention a blue graph?
Does OCR support it?
Does the transcript explain why it was drawn?
Are there multiple possible matches?
```

If evidence is weak, it lowers confidence.

## 14. Temporal Reasoning

The Temporal Reasoner connects the timeline.

It figures out:

```text
Before: lecturer introduced cats and dogs
During: he drew the blue graph
After: he explained the comparison
Later: he returned to the same idea
```

This prevents shallow answers.

## 15. Answer Generation

The Answer Generator creates the final answer.

Example:

```text
The moment you remember is around 02:41:16. He drew the blue graph while
comparing cats and dogs to explain how feature differences can be visualized.
The explanation begins slightly earlier at 02:40:52 and continues until about
02:43:22.
```

It includes:

```text
timestamp
answer
citations
confidence
related moments
```

## 16. Final Output To User

Frontend displays:

```text
answer
clickable timestamp
video jump button
evidence panel
confidence score
related timeline moments
```

So the user can click:

```text
Jump to 02:41:16
```

and watch the exact moment.

## Complete Flow

```text
Upload video
 -> create video_id and manifest
 -> extract audio
 -> transcribe audio
 -> extract boundary signals
 -> create canonical non-overlapping atomic spans
 -> validate complete timeline coverage
 -> extract frames and clips
 -> run OCR and visual analysis
 -> group chunks into events
 -> group events into chapters
 -> build world memory
 -> store vectors in ChromaDB
 -> user asks question
 -> planner decides search strategy
 -> retriever finds evidence
 -> verifier checks evidence
 -> temporal reasoner connects timelines
 -> answer generator responds
 -> confidence evaluator scores answer
 -> frontend shows answer and timestamp
```
