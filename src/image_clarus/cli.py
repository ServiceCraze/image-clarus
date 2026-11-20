import argparse
import sys
from importlib.metadata import PackageNotFoundError, version


class OnceAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            raise argparse.ArgumentError(self, "may only be specified once")
        setattr(namespace, self.dest, values)


class VersionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            installed_version = version("image-clarus")
        except PackageNotFoundError:
            parser.exit(
                2, "image-clarus: installation error: version metadata unavailable\n"
            )
        print(f"image-clarus {installed_version}")
        parser.exit()


class _SignalInterrupt(BaseException):
    pass


def main():
    import signal
    from types import SimpleNamespace

    from image_clarus.pipeline import StopToken

    state = SimpleNamespace(stop=StopToken(), interruptible=False)
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def request(signum, frame):
        first = state.stop.signum is None
        state.stop.request(signum)
        if first and state.interruptible:
            state.interruptible = False
            raise _SignalInterrupt

    try:
        for sig in handlers:
            signal.signal(sig, request)
        try:
            result = _main(state)
            return 128 + state.stop.signum if state.stop.signum is not None else result
        except _SignalInterrupt:
            return 128 + state.stop.signum
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def _main(state):
    parser = argparse.ArgumentParser(prog="image-clarus", allow_abbrev=False)
    parser.add_argument("--version", action=VersionAction, nargs=0)
    subparsers = parser.add_subparsers(dest="command", required=True)
    process = subparsers.add_parser(
        "process",
        help="Process one image",
        description="Description and JSON outputs are create-only by default; XMP uses configured policies; search is a help-only stub.",
        allow_abbrev=False,
    )
    process.add_argument("IMAGE")
    process.add_argument("--config", metavar="FILE", action=OnceAction)
    process.add_argument(
        "--stages",
        metavar="STAGES",
        action=OnceAction,
        help="Default: desc,json,xmp; explicit subsets do not add prerequisites",
    )
    process.add_argument("--set", metavar="PATH=VALUE", action="append")
    process.add_argument("--state-dir", metavar="DIR", action=OnceAction)
    for option in ("--desc-prompt", "--json-prompt", "--json-schema"):
        process.add_argument(option, metavar="FILE", action=OnceAction)
    process.add_argument("--regenerate", action="store_true")
    process.add_argument(
        "--missing-prerequisite",
        choices=("fail", "skip"),
        action=OnceAction,
        help="Default: fail",
    )
    subparsers.add_parser(
        "search", help="Search (not implemented in Slice 1)", allow_abbrev=False
    )
    args = parser.parse_args()
    if args.command == "search":
        print("search is not implemented in Slice 1", file=sys.stderr)
    else:
        import os
        from pathlib import Path

        try:
            if any(character in args.IMAGE for character in "*?["):
                raise ValueError
            image = Path(args.IMAGE).expanduser().resolve(strict=True)
            if not image.is_file() or not os.access(image, os.R_OK):
                raise ValueError
        except (OSError, ValueError, RuntimeError):
            print("image-clarus: invalid image path", file=sys.stderr)
            return 2
        from types import SimpleNamespace

        from image_clarus.artifacts import ArtifactService
        from image_clarus.config import resolve_config
        from image_clarus.pipeline import STAGE_REGISTRY, run_pipeline
        from image_clarus.providers.openai_compatible import OpenAICompatible
        from image_clarus.stages.description import run_description
        from image_clarus.stages.structure import run_structure

        selected = (
            tuple(item.strip() for item in args.stages.split(","))
            if args.stages is not None
            else STAGE_REGISTRY
        )
        if (
            not selected
            or len(set(selected)) != len(selected)
            or not set(selected) <= set(STAGE_REGISTRY)
        ):
            print("image-clarus: invalid stage selection", file=sys.stderr)
            return 2
        selected = tuple(stage for stage in STAGE_REGISTRY if stage in selected)
        from image_clarus.config import ConfigurationError

        try:
            state.interruptible = True
            if state.stop.signum is not None:
                return 128 + state.stop.signum
            config = resolve_config(
                stages=selected,
                config_file=args.config,
                json_schema=args.json_schema,
                desc_prompt=args.desc_prompt,
                json_prompt=args.json_prompt,
                overrides=args.set or (),
                missing_prerequisite=args.missing_prerequisite,
                regenerate=args.regenerate,
                state_dir=args.state_dir,
            )
        except ConfigurationError as error:
            print(f"image-clarus: {error}", file=sys.stderr)
            return 1 if error.category == "authentication" else 2
        finally:
            state.interruptible = False

        import logging

        logging.basicConfig(level=config["logging"]["level"], stream=sys.stderr)

        secrets = set()
        for provider in config.get("providers", {}).values():
            key = provider.get("api_key")
            env_name = provider.get("api_key_env")
            if env_name:
                secrets.add(os.environ.get(env_name, ""))
            if key:
                secrets.add(key)
        secrets.discard("")

        def redact(value):
            for secret in sorted(secrets, key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
            return value

        from image_clarus.providers.openai_compatible import ProviderError
        from image_clarus.results import StageResult

        stop = state.stop

        class InterruptibleProvider:
            def __init__(self, provider, model):
                self.client = OpenAICompatible(provider, model)

            def _call(self, method, **kwargs):
                if stop.signum is not None:
                    raise ProviderError("interrupted")
                try:
                    state.interruptible = True
                    if stop.signum is not None:
                        raise ProviderError("interrupted")
                    result = getattr(self.client, method)(**kwargs)
                except _SignalInterrupt:
                    raise ProviderError("interrupted") from None
                except ProviderError:
                    if stop.signum is not None:
                        raise ProviderError("interrupted") from None
                    raise
                finally:
                    state.interruptible = False
                if stop.signum is not None:
                    raise ProviderError("interrupted")
                return result

            def image(self, **kwargs):
                return self._call("image", **kwargs)

            def structured(self, **kwargs):
                return self._call("structured", **kwargs)

        def stage_wrapper(name, function):
            def run(image_path, stage_config, stage_services):
                outcome = function(image_path, stage_config, stage_services)
                if stop.signum is not None and outcome.status != "completed":
                    return StageResult(name, "skipped", reason_code="interrupted")
                return outcome

            return run

        from image_clarus.artifacts import ArtifactError

        class InterruptibleArtifacts(ArtifactService):
            def write(self, *args, **kwargs):
                if stop.signum is not None:
                    raise ArtifactError("interrupted")
                return super().write(*args, **kwargs)

        services = SimpleNamespace(
            artifacts=InterruptibleArtifacts(config["pipeline"]["backup_retention"]),
            provider_factory=InterruptibleProvider,
            stop=stop,
        )
        stage_functions = {
            "desc": stage_wrapper("desc", run_description),
            "json": stage_wrapper("json", run_structure),
        }
        if "xmp" in selected:
            from image_clarus.stages.xmp import run_xmp

            stage_functions["xmp"] = stage_wrapper("xmp", run_xmp)

        result = run_pipeline(
            image,
            config,
            services,
            stage_functions,
            selected=selected,
            stop=stop,
        )
        for stage in result.stages:
            if stage.status == "completed":
                import json

                print(
                    f"{stage.stage}: completed — output={json.dumps(redact(str(stage.output_path)))}"
                )
            elif stage.status == "failed":
                message = " ".join(redact(stage.message).splitlines())
                print(
                    f"{stage.stage}: failed — category={redact(stage.error_category)}; message={message}"
                )
            else:
                print(f"{stage.stage}: skipped — reason={redact(stage.reason_code)}")
        return result.exit_code
    return 3
