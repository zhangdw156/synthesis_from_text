You are given a multi-turn tool-use trajectory. Please evaluate the trajectory according to the following rubrics.
Your job is to score the trajectory on the following binary rubrics.
For EACH rubric, you must output 0 or 1 only, according to the criteria below.
For each rubric, if there is no hallucination of the following content throughout the entire trajectory, the corresponding rubric score is 1.
If any single round does not meet (the condition), the corresponding rubric should be scored as 0. Be strict in your evaluation.

## Rubric
R1: Tool-call hallucination
- Check whether any tool call uses argument values that are not provided or reasonably derivable from the dialogue context.

R2: Capability hallucination
Check whether the assistant makes incorrect claims about what can or cannot be done.
- H2-a False inability: The user request IS solvable using the available tools, but the assistant claims it cannot be done or refuses without justification.
- H2-b Missing limitation disclosure: The user request is NOT solvable with the available tools, but the assistant proceeds as if it is solvable, or fails to clearly explain the limitation and offer the closest feasible alternative.

R3: Context hallucination
Check whether the assistant misinterprets the ongoing context or references things that are not true in the dialogue.
- Wrongly referencing previous user constraints, preferences, or decisions.
- Cross-turn inconsistency: changing entities/values (IDs, counts, dates, constraints) without new evidence or tool output.
- Conflicting summaries: later summary contradicts earlier established facts.

## Input
{trajectory}

## Output Format
Return a single JSON object with EXACTLY these keys and integer values 0 or 1:

{
  "R1": 0 or 1,
  "R2": 0 or 1,
  "R3": 0 or 1
}

Do NOT output anything else (no explanations, no comments).