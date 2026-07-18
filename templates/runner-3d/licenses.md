# 素材许可记录（汪汪跑酷 3D）

## 3D 模型（models/ 目录）

| 文件 | 来源包 | 作者 | 许可 |
|---|---|---|---|
| Tree1-4.glb, Bush1-3.glb, Rock1-2.glb, Grass1.glb | Nature Pack Essentials vol.3 | Quaternius | CC0 1.0 |
| Fence.glb, Fence2.glb | Farm Buildings (Sept 2018) | Quaternius | CC0 1.0 |
| CargoTrain_Front/Wagon/Container.glb | Train Pack (April 2019) | Quaternius | CC0 1.0 |
| kenney_crate.glb | Platformer Kit | Kenney | CC0 1.0 |

- 作者站点：https://quaternius.com 、https://kenney.nl （CC0 公共领域，可商用，无需署名）
- 获取镜像：https://github.com/beep2bleep/FreeAssetsByKenneyNLandQuaternius
- 处理管线：FBX → FBX2glTF（GLB）→ 运行时转 MeshLambertMaterial + 反向壳描边；
  火车 Main/DarkMain 材质按车道动态重配色；Kenney 模型自带贴图运行时保留。
- 城市主题改版（b250718-5）起停用 Quaternius 郊区房（Buildings pack），两侧楼群/围墙/龙门架/信号机为程序化建模。

## UI 素材（根目录 PNG/TTF）

- btn_red / btn_green / chip_grey / star / star_o / play.png, kenney.ttf：Kenney UI Pack，CC0 1.0，https://kenney.nl

## 项目自有素材

- puppy.png, sky.png, bone.png：AI 生成为本项目定制；index.html 内程序化纹理（轨道/草地/云/影子）。
