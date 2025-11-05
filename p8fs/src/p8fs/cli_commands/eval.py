"""Eval command for running evaluation agents with structured output."""

import importlib
import json
import sys
from pathlib import Path
from p8fs_cluster.logging import get_logger
from p8fs.services.llm import CallingContext, MemoryProxy
from p8fs.utils.json_extractor import JSONExtractor

logger = get_logger(__name__)


async def eval_command(args):
    """Execute eval agent on content with structured output."""
    try:
        # Load agent model by reflection
        logger.info(f"Loading agent model: {args.agent_model}")

        # Parse model name
        if "." in args.agent_model:
            # Full or partial module path
            parts = args.agent_model.rsplit(".", 1)
            if len(parts) == 2:
                module_path, class_name = parts
                # Handle shorthand like "p8.DreamModel"
                if module_path == "p8":
                    module_path = "p8fs.models.p8"
                elif not module_path.startswith("p8fs."):
                    module_path = f"p8fs.models.{module_path}"
            else:
                logger.error(f"Invalid model path: {args.agent_model}")
                return 1
        else:
            # Simple name, search in common locations
            class_name = args.agent_model
            # Try agentlets first
            module_path = "p8fs.models.agentlets.dreaming"

        try:
            module = importlib.import_module(module_path)
            agent_model = getattr(module, class_name)
            model_name = agent_model.get_model_name() if hasattr(agent_model, 'get_model_name') else agent_model.__name__
            logger.info(f"Loaded model: {model_name} from {module_path}")
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load model {args.agent_model}: {e}")
            print(f"❌ Failed to load model {args.agent_model}", file=sys.stderr)
            print(f"   Error: {e}", file=sys.stderr)
            print(f"\nTry one of:", file=sys.stderr)
            print(f"  - DreamModel (searches in agentlets)", file=sys.stderr)
            print(f"  - p8.Agent (from p8fs.models.p8)", file=sys.stderr)
            print(f"  - models.agentlets.dreaming.DreamModel (full path)", file=sys.stderr)
            return 1

        # Read file content
        if not args.file:
            print("❌ --file is required", file=sys.stderr)
            return 1

        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File not found: {args.file}", file=sys.stderr)
            return 1

        content = file_path.read_text()
        logger.info(f"Read {len(content)} characters from {args.file}")

        # Initialize MemoryProxy with agent model
        proxy = MemoryProxy(agent_model)

        # Get model description with structured schema
        system_prompt = agent_model.get_model_description(
            use_full_description=True,
            schema_format=args.schema_format
        )

        # Create calling context
        # If output format is json or yaml, force JSON response from LLM
        # NOTE: Claude sometimes has issues with prefer_json + function calling
        # so we only enable it for non-Claude models for now
        prefer_json = args.format in ["json", "yaml"] and "gpt" in args.model.lower()

        context = CallingContext(
            model=args.model,
            temperature=0.1,  # Lower for structured output
            tenant_id=args.tenant_id,
            stream=False,  # Non-streaming for structured output
            prefer_json=prefer_json  # Force JSON response format for structured output
        )

        # Build prompt with content
        question = f"Please analyze the following content:\n\n{content}"

        logger.info(f"Running eval with model {args.model}...")
        model_name = agent_model.get_model_name() if hasattr(agent_model, 'get_model_name') else agent_model.__name__
        print(f"📊 Analyzing content with {model_name}...", file=sys.stderr)

        # Run the model with sufficient iterations for agentic loop
        response = await proxy.run(question, context, max_iterations=5)

        # Parse JSON response using utility
        try:
            result_json = JSONExtractor.extract(response)

            if result_json:
                # Debug: Log extracted JSON
                logger.info(f"Extracted JSON keys: {list(result_json.keys())}")
                logger.info(f"Sample values - executive_summary: {result_json.get('executive_summary', 'N/A')[:100] if result_json.get('executive_summary') else 'None'}")
                logger.info(f"Sample values - goals count: {len(result_json.get('goals', []))}")
                logger.info(f"Sample values - pending_tasks count: {len(result_json.get('pending_tasks', []))}")

                # Try to validate against model, but save JSON even if validation fails
                validated_result = None
                try:
                    validated_result = agent_model(**result_json)
                    logger.info("✅ Successfully validated structured output")
                except Exception as e:
                    logger.warning(f"Validation failed: {e}. Will save unvalidated JSON as YAML.")

                # Determine what to output
                if validated_result:
                    # Use validated model
                    output_data = json.loads(validated_result.model_dump_json())
                else:
                    # Use raw JSON (unvalidated)
                    output_data = result_json

                # Output results
                if args.output:
                    output_path = Path(args.output)
                    if args.format == "yaml":
                        import yaml
                        with open(output_path, 'w') as f:
                            yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)
                        status = "✅ Saved validated YAML" if validated_result else "⚠️  Saved unvalidated YAML"
                        print(f"{status} output to {output_path}")
                    elif args.format == "json":
                        with open(output_path, 'w') as f:
                            json.dump(output_data, f, indent=2)
                        status = "✅ Saved validated JSON" if validated_result else "⚠️  Saved unvalidated JSON"
                        print(f"{status} output to {output_path}")
                    else:
                        with open(output_path, 'w') as f:
                            f.write(response)
                        print(f"✅ Saved raw output to {output_path}")
                else:
                    # Print to stdout
                    if args.format == "yaml":
                        import yaml
                        print(yaml.dump(output_data, default_flow_style=False, sort_keys=False))
                    elif args.format == "json":
                        print(json.dumps(output_data, indent=2))
                    else:
                        print(response)

                return 0
            else:
                logger.warning("Could not parse structured output, returning raw response")
                print(f"⚠️  Could not parse structured output", file=sys.stderr)

                if args.output:
                    Path(args.output).write_text(response)
                    print(f"Saved raw output to {args.output}")
                else:
                    print(response)

                return 1

        except Exception as e:
            logger.error(f"Failed to parse structured output: {e}")
            print(f"❌ Failed to parse response: {e}", file=sys.stderr)

            if args.output:
                Path(args.output).write_text(response)
                print(f"Saved raw output to {args.output}")
            else:
                print("\nRaw response:")
                print(response)

            return 1

    except Exception as e:
        logger.error(f"Eval command failed: {e}", exc_info=True)
        print(f"❌ Eval error: {e}", file=sys.stderr)
        return 1
