"""Build, tag, and push one image per unique (dockerfile, context)."""


def build_and_push(plan, registry, run):
    run(["az", "acr", "login", "--name", registry.split(".")[0]])
    tags = plan["tags"]
    for build in plan["builds"]:
        first, rest = build["keys"][0], build["keys"][1:]
        run(["docker", "build", "-f", build["file"], "-t", tags[first], build["context"]])
        for key in rest:
            run(["docker", "tag", tags[first], tags[key]])
        for key in build["keys"]:
            run(["docker", "push", tags[key]])
