You are rewriting a complex, realistic multi-turn tool-use trajectory for agenic training.
Goal: The trajectory should be complex, natural, no-hallucination and show the wisdom of the assistant.
It must show the assistant’s ability for correct tool use, reasoning, context understanding, and communication skills with users.
Please carefully consider what problems exist with the existing synthetic trajectories and how to improve them to create high-quality trajectories.
You can follow the following guidelines.

# Guideline

### System Prompt Complexity
You need to refine and upgrade the constraints of the system prompts to make them more structured, systematic, and consistent with real-world logic, in order to fully test the agent’s ability to make correct tool calls in complex scenarios. You also need to define the database schema in the system prompts, and the data structure returned by the tool will be based on this.

### User Request Complexity & Naturalness
- Natural: Natural requests may include colloquial language, implied context, vague references to prior steps, or real-world motivations (e.g., saving time/money, lose weight). Avoid overly formal or purely instructional language.
- User diversity: Create a user profile and maintain the user’s personality and characteristics throughout the conversation history.
- Requires Deep Analysis & Reasoning: The user’s request must necessitate careful analysis and multi-step reasoning to identify the correct tool(s) and determine appropriate parameter values.
- Requires Analysis of Tool Dependencies & Outputs: The request should force the assistant to understand dependencies between tools and use outputs from previous steps to decide which tool to invoke next.
- In at least 1 turn, the user’s request contains multiple constraints, including explicit constraints, implicit requirements that require the assistant to infer.
- In at least 1 turn, The user asks a question that can only be answered by reasoning across outputs from multiple tool calls in the long context.
- Challenging Pitfalls: **MUST INCLUDE AT LEAST 1-2 PITFALLs** for one trajectory.
  This pattern sets traps to test the assistant’s ability to correctly make robust tool calls based on rules, constraints or user preferences.
  The trajectory must include request for this kind of challenging tool calls, and the assistant must explicitly analyze and identify these pitfalls to achieve robust tool calls.

### Assistant Intelligibility
Demonstrate the following capabilities of the assistant:

(1) Communication Skills
- User Intent Understanding: Accurately interpret the underlying goals and context of the user’s request.
- Confirmation & Clarification: Proactively confirm key details & ask the user to clarify ambiguous information when necessary.
- Capability Limitation Awareness: Clearly communicate the boundaries and limitations of the assistant’s available capabilities.
- Result Explanation & Summarization: Interpret, distill, and present tool outputs or complex information in a structured, understandable manner.
- Proactive Assistance: Anticipate potential user needs based on context and offer helpful suggestions in advance.

(2) Robust Tool-Calling Capability
- Tool Selection: Choose the most appropriate tool from the available set based on taskrequirements.
- Sequential Tool Usage: Plan and execute multi-tool workflows with correct dependencies and order.
- Parameter Handling: Correctly construct and validate complex argument structures (e.g., nested objects, lists), respecting type, range, and format constraints.
- Result Analysis: Parse and evaluate tool responses, extract relevant information, and determine validity for subsequent steps.
- State Tracking: Maintain awareness of completed and pending steps in a multi-step task.
- Constraint Analysis: Identify and adhere to real-world constraints and business rules (e.g., date ranges, mutually exclusive fields, batch limits).
- Error Handling: Gracefully manage tool failures, diagnose error causes, and adjust strategy or inform the user appropriately.
- Context Management: Effectively retain and utilize conversation history to ensure coherence across complex interactions.

(3) Reasoning & Execution Ability
- Planning & Task Decomposition: Break down complex or vague user requests into clear, executable step-by-step plans.
- Prerequisite Management: Recognize and acquire necessary information or conditions before executing tasks (e.g., querying environment, requesting user input).
- Verification and Validation: Perform essential checks before critical operations, such as exploring available tools, confirming permissions, or validating inputs.

### Realistic & Complex Environment
IMPORTANT NOTES:
- The tool called in the trajectory MUST exist in candidate toolsets, with the parameter type and value correct.
- If it’s necessary to add tools when constructing complex trajectories, you can add them in the final output tools block.

GOALS:
- This increases the difficulty of choosing tools. A diverse range of tools must be included, specifically reading and writing tools.
- Increase the difficulty of making totally correct tool calls (parameter type, value). For example, include structured inputs (list, dict, nested objects) and meaningful constraints.
- The tools should conform to the database schema as much as possible (may defined in system prompt), and mainly include read-write tools. You can add & modify tools.
- Unique: Tool call parameters should use unique database fields (such as user ID, product ID, etc.) as much as possible to mimic real logic.
- Realistic: Always avoid using empty placeholders. For example, do not return something like "5+ more results ...", "path=/example".
- Success Response: A success response should only be returned if the tool call is correct. The tool’s response must return a complete data structure in a well-structured format (e.g., JSON).
- Error Response: You are allowed to simulate non-simple errors that might occur in the real world. The tool’s response must return a concise error message. Avoid directly telling the assistant how to solve the problem.

### Trajectory Diversity
- Reduce the frequency of repeatedly using certain tools to solve problems, avoiding the reduction of trajectory diversity, and retain only the most valuable trajectories for learning.
- Include but not limited to the following pattern, and make the following pattern more difficult, diverse and natural.
  - [Pattern 1: Environment Complexity]
    - [1.1: Error Recovery] In multi-turn function calling, models may encounter errors, such as invalid input or failed execution that require recovery. If you think of any suitable, non-trivial, real-world scenario errors, please include this pattern.
    - [1.2: Long Context] Introduce large volumes of extraneous data to test how well the model can extract crucial details from an overwhelming array of information.
  - [Pattern 2: Clarification] Tests the model’s ability to recognize when essential information is missing from the user request.
    - [2.1: Can be inferred from the system] The assistant actively explore ways to find the essential information and complete the task
    - [2.2: Can not be inferred from the system] The assistant actively clarifies the situation.
  - [Pattern 3: Identify Limitation] Requires the model to identify that no available function can fulfill the user request.
  - [Pattern 4: Assistant guides user operation] For example, if a user reports no internet access, the assistant uses tool calls to discover that the SIM card is not inserted, and then guides the user to insert it (this process cannot be performed by the assistant alone due to real-world physical constraints and requires active communication and guidance between the assistant and the user).

# Input Data
Toolset: {tools}
Trajectory: {our_traj}

# Output Requirement
- Reduce redundancy: Reduce the frequency of repeatedly using certain tools to solve problems, avoiding the reduction of trajectory diversity, and retain only the most valuable trajectories for learning.
- Preserve turn order.
  - The assistant can only call the tool once per round.
  - Each tool message must be followed by an assistant message.
  - If an assistant message contains a tool call, it must be followed by a tool message (tool result).
  - Tool messages must not be followed directly by user messages.
- If the original trajectory violates these rules or misuses tools, fix it in the rewritten version.
- Output all candidate tools (the original tools + new tools if needed)
- You must strictly follow the following output format.

# Output format
<toolsets>
All candidate tools in JSON, OPENAI format.
[
    {
        "name": "",
        "description": "",
        "inputSchema": {
            "type": "",
            "properties": { },
            "required": []
        }
    },
    ...
]
</toolsets>

<system>
[role and domain rules here]
</system>
<user>
...
</user>
<assistant>
...
<func>
{{"name": "...", "arguments": {{...}}}}
</func>
</assistant>
<tool>
[concrete tool response in JSON format if tool calls are made]
</tool>
<assistant>
...
</assistant>

...
(more conversations here)