[1mdiff --git a/neuro_flow/ast.py b/neuro_flow/ast.py[m
[1mindex 54d236b..baf2340 100644[m
[1m--- a/neuro_flow/ast.py[m
[1m+++ b/neuro_flow/ast.py[m
[36m@@ -59,6 +59,8 @@[m [mclass Image(Base):[m
     context: OptLocalPathExpr[m
     dockerfile: OptLocalPathExpr[m
     build_args: Optional[Sequence[StrExpr]] = field(metadata={"allow_none": True})[m
[32m+[m[32m    env: Optional[Mapping[str, StrExpr]] = field(metadata={"allow_none": True})[m
[32m+[m[32m    volumes: Optional[Sequence[OptStrExpr]] = field(metadata={"allow_none": True})[m
 [m
 [m
 @dataclass(frozen=True)[m
[1mdiff --git a/neuro_flow/context.py b/neuro_flow/context.py[m
[1mindex 992f570..ea85647 100644[m
[1m--- a/neuro_flow/context.py[m
[1m+++ b/neuro_flow/context.py[m
[36m@@ -201,6 +201,8 @@[m [mclass ImageCtx:[m
     dockerfile: Optional[LocalPath][m
     full_dockerfile_path: Optional[LocalPath][m
     build_args: Sequence[str][m
[32m+[m[32m    env: Mapping[str, str][m
[32m+[m[32m    volumes: Sequence[str][m
 [m
 [m
 @dataclass(frozen=True)[m
[36m@@ -354,6 +356,8 @@[m [mclass BaseFlowContext(BaseContext):[m
                     local=local_path,[m
                     full_local_path=calc_full_path(ctx, local_path),[m
                 )[m
[32m+[m[32m        ctx = replace(ctx, _volumes=volumes)[m
[32m+[m
         images = {}[m
         if ast_flow.images is not None:[m
             for k, i in ast_flow.images.items():[m
[36m@@ -363,6 +367,18 @@[m [mclass BaseFlowContext(BaseContext):[m
                     build_args = [await v.eval(ctx) for v in i.build_args][m
                 else:[m
                     build_args = [][m
[32m+[m
[32m+[m[32m                image_env = {}[m
[32m+[m[32m                if i.env is not None:[m
[32m+[m[32m                    image_env.update({k: await v.eval(ctx) for k, v in i.env.items()})[m
[32m+[m
[32m+[m[32m                image_volumes = [][m
[32m+[m[32m                if i.volumes is not None:[m
[32m+[m[32m                    for vol in i.volumes:[m
[32m+[m[32m                        value = await vol.eval(ctx)[m
[32m+[m[32m                        if value:[m
[32m+[m[32m                            image_volumes.append(value)[m
[32m+[m
                 images[k] = ImageCtx([m
                     id=k,[m
                     ref=await i.ref.eval(ctx),[m
[36m@@ -371,10 +387,11 @@[m [mclass BaseFlowContext(BaseContext):[m
                     dockerfile=dockerfile_path,[m
                     full_dockerfile_path=calc_full_path(ctx, dockerfile_path),[m
                     build_args=build_args,[m
[32m+[m[32m                    env=image_env,[m
[32m+[m[32m                    volumes=image_volumes,[m
                 )[m
         return replace(  # type: ignore[return-value][m
             ctx,[m
[31m-            _volumes=volumes,[m
             _images=images,[m
         )[m
 [m
[1mdiff --git a/neuro_flow/live_runner.py b/neuro_flow/live_runner.py[m
[1mindex c179314..646c699 100644[m
[1m--- a/neuro_flow/live_runner.py[m
[1m+++ b/neuro_flow/live_runner.py[m
[36m@@ -479,6 +479,10 @@[m [mclass LiveRunner(AsyncContextManager["LiveRunner"]):[m
         cmd.append(f"--file={rel_dockerfile_path}")[m
         for arg in image_ctx.build_args:[m
             cmd.append(f"--build-arg={arg}")[m
[32m+[m[32m        for vol in image_ctx.volumes:[m
[32m+[m[32m            cmd.append(f"--volume={vol}")[m
[32m+[m[32m        for k, v in image_ctx.env.items():[m
[32m+[m[32m            cmd.append(f"--env={k}={v}")[m
         cmd.append(str(image_ctx.full_context_path))[m
         cmd.append(str(image_ctx.ref))[m
         await self._run_subproc("neuro-extras", "image", "build", *cmd)[m
[1mdiff --git a/neuro_flow/parser.py b/neuro_flow/parser.py[m
[1mindex 80d16dd..efe58bc 100644[m
[1m--- a/neuro_flow/parser.py[m
[1m+++ b/neuro_flow/parser.py[m
[36m@@ -442,6 +442,8 @@[m [mdef parse_image(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Image:[m
             "context": OptLocalPathExpr,[m
             "dockerfile": OptLocalPathExpr,[m
             "build_args": SimpleSeq(StrExpr),[m
[32m+[m[32m            "env": SimpleMapping(StrExpr),[m
[32m+[m[32m            "volumes": SimpleSeq(OptStrExpr),[m
         },[m
         ast.Image,[m
     )[m
[1mdiff --git a/tests/unit/live-full.yml b/tests/unit/live-full.yml[m
[1mindex 14f2dd6..1a5e78b 100644[m
[1m--- a/tests/unit/live-full.yml[m
[1m+++ b/tests/unit/live-full.yml[m
[36m@@ -9,6 +9,10 @@[m [mimages:[m
     - --arg1[m
     - val1[m
     - --arg2=val2[m
[32m+[m[32m    env:[m
[32m+[m[32m      SECRET_ENV: secret:key[m
[32m+[m[32m    volumes:[m
[32m+[m[32m      - ${{ volumes.volume_sec.ref_ro }}[m
 volumes:[m
   volume_a:[m
     remote: storage:dir[m
[36m@@ -18,6 +22,9 @@[m [mvolumes:[m
   volume_b:[m
     remote: storage:other[m
     mount: /var/other[m
[32m+[m[32m  volume_sec:[m
[32m+[m[32m    remote: secret:key[m
[32m+[m[32m    mount: /var/secret/key.txt[m
 defaults:[m
   tags: [tag-a, tag-b][m
   env:[m
[1mdiff --git a/tests/unit/test_batch_parser.py b/tests/unit/test_batch_parser.py[m
[1mindex 2880650..a5bc6de 100644[m
[1m--- a/tests/unit/test_batch_parser.py[m
[1m+++ b/tests/unit/test_batch_parser.py[m
[36m@@ -60,6 +60,8 @@[m [mdef test_parse_minimal(assets: pathlib.Path) -> None:[m
                         Pos(0, 0, config_file), Pos(0, 0, config_file), "--arg2=val2"[m
                     ),[m
                 ],[m
[32m+[m[32m                env=None,[m
[32m+[m[32m                volumes=None,[m
             )[m
         },[m
         volumes={[m
[1mdiff --git a/tests/unit/test_context.py b/tests/unit/test_context.py[m
[1mindex fb659c9..efeeb03 100644[m
[1m--- a/tests/unit/test_context.py[m
[1m+++ b/tests/unit/test_context.py[m
[36m@@ -61,7 +61,7 @@[m [masync def test_volumes(assets: pathlib.Path) -> None:[m
     config_file = workspace / "live-full.yml"[m
     flow = parse_live(workspace, config_file)[m
     ctx = await LiveContext.create(flow, workspace, config_file)[m
[31m-    assert ctx.volumes.keys() == {"volume_a", "volume_b"}[m
[32m+[m[32m    assert ctx.volumes.keys() == {"volume_a", "volume_b", "volume_sec"}[m
 [m
     assert ctx.volumes["volume_a"].id == "volume_a"[m
     assert ctx.volumes["volume_a"].remote == URL("storage:dir")[m
[36m@@ -98,6 +98,8 @@[m [masync def test_images(assets: pathlib.Path) -> None:[m
     assert ctx.images["image_a"].dockerfile == LocalPath("dir/Dockerfile")[m
     assert ctx.images["image_a"].full_dockerfile_path == workspace / "dir/Dockerfile"[m
     assert ctx.images["image_a"].build_args == ["--arg1", "val1", "--arg2=val2"][m
[32m+[m[32m    assert ctx.images["image_a"].env == {"SECRET_ENV": "secret:key"}[m
[32m+[m[32m    assert ctx.images["image_a"].volumes == ["secret:key:/var/secret/key.txt:ro"][m
 [m
 [m
 async def test_defaults(assets: pathlib.Path) -> None:[m
[1mdiff --git a/tests/unit/test_live_parser.py b/tests/unit/test_live_parser.py[m
[1mindex 4ba0074..8be2c88 100644[m
[1m--- a/tests/unit/test_live_parser.py[m
[1m+++ b/tests/unit/test_live_parser.py[m
[36m@@ -97,7 +97,7 @@[m [mdef test_parse_full(assets: pathlib.Path) -> None:[m
     flow = parse_live(workspace, config_file)[m
     assert flow == ast.LiveFlow([m
         Pos(0, 0, config_file),[m
[31m-        Pos(53, 0, config_file),[m
[32m+[m[32m        Pos(60, 0, config_file),[m
         id=SimpleOptIdExpr([m
             Pos(0, 0, config_file),[m
             Pos(0, 0, config_file),[m
[36m@@ -112,7 +112,7 @@[m [mdef test_parse_full(assets: pathlib.Path) -> None:[m
         images={[m
             "image_a": ast.Image([m
                 Pos(4, 4, config_file),[m
[31m-                Pos(11, 0, config_file),[m
[32m+[m[32m                Pos(15, 0, config_file),[m
                 ref=StrExpr([m
                     Pos(0, 0, config_file), Pos(0, 0, config_file), "image:banana"[m
                 ),[m
[36m@@ -129,12 +129,24 @@[m [mdef test_parse_full(assets: pathlib.Path) -> None:[m
                         Pos(0, 0, config_file), Pos(0, 0, config_file), "--arg2=val2"[m
                     ),[m
                 ],[m
[32m+[m[32m                env={[m
[32m+[m[32m                    "SECRET_ENV": StrExpr([m
[32m+[m[32m                        Pos(0, 0, config_file), Pos(0, 0, config_file), "secret:key"[m
[32m+[m[32m                    ),[m
[32m+[m[32m                },[m
[32m+[m[32m                volumes=[[m
[32m+[m[32m                    OptStrExpr([m
[32m+[m[32m                        Pos(0, 0, config_file),[m
[32m+[m[32m                        Pos(0, 0, config_file),[m
[32m+[m[32m                        "${{ volumes.volume_sec.ref_ro }}",[m
[32m+[m[32m                    ),[m
[32m+[m[32m                ],[m
             )[m
         },[m
         volumes={[m
             "volume_a": ast.Volume([m
[31m-                Pos(13, 4, config_file),[m
[31m-                Pos(17, 2, config_file),[m
[32m+[m[32m                Pos(17, 4, config_file),[m
[32m+[m[32m                Pos(21, 2, config_file),[m
                 remote=URIExpr([m
                     Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:dir"[m
                 ),[m
[36m@@ -149,8 +161,8 @@[m [mdef test_parse_full(assets: pathlib.Path) -> None:[m
                 ),[m
             ),[m
             "volume_b": ast.Volume([m
[31m-                Pos(18, 4, config_file),[m
[31m-                Pos(20, 0, config_file),[m
[32m+[m[32m                Pos(22, 4, config_file),[m
[32m+[m[32m                Pos(24, 2, config_file),[m
                 remote=URIExpr([m
                     Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:other"[m
                 ),[m
[36m@@ -164,10 +176,28 @@[m [mdef test_parse_full(assets: pathlib.Path) -> None:[m
                     Pos(0, 0, config_file), Pos(0, 0, config_file), None[m
                 ),[m
             ),[m
[32m+[m[32m            "volume_sec": ast.Volume([m
[32m+[m[32m                Pos(25, 4, config_file),[m
[32m+[m[32m                Pos(27, 0, config_file),[m
[32m+[m[32m                remote=URIExpr([m
[32m+[m[32m                    Pos(0, 0, config_file), Pos(0, 0, config_file), "secret:key"[m
[32m+[m[32m                ),[m
[32m+[m[32m                mount=RemotePathExpr([m
[32m+[m[32m                    Pos(0, 0, config_file),[m
[32m+[m[32m                    Pos(0, 0, config_file),[m
[32m+[m[32m                    "/var/secret/key.txt",[m
[32m+[m[32m                ),[m
[32m+[m[32m                read_only=OptBoolExpr([m
[32m+[m[32m                    Pos(0, 0, config_file), Pos(0, 0, config_file), None[m
[32m+[m[32m                ),[m
[32m+[m[32m                local=OptLocalPathExpr([m
[32m+[m[32m                    Pos(0, 0, config_file), Pos(0, 0, config_file), None[m
[32m+[m[32m                ),[m
[32m+[m[32m            ),[m
         },[m
         defaults=ast.FlowDefaults([m
[31m-            Pos(21, 2, config_file),[m
[31m-            Pos(28, 0, config_file),[m
[32m+[m[32m            Pos(28, 2, config_file),[m
[32m+[m[32m            Pos(35, 0, config_file),[m
             tags=[[m
                 StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-a"),[m
                 StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-b"),[m
[36m@@ -192,8 +222,8 @@[m [mdef test_parse_full(assets: pathlib.Path) -> None:[m
         ),[m
         jobs={[m
             "test_a": ast.Job([m
[31m-                Pos(30, 4, config_file),[m
[31m-                Pos(53, 0, config_file),[m
[32m+[m[32m                Pos(37, 4, config_file),[m
[32m+[m[32m                Pos(60, 0, config_file),[m
                 name=OptStrExpr([m
                     Pos(0, 0, config_file), Pos(0, 0, config_file), "job-name"[m
                 ),[m
