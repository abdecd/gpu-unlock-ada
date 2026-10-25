# 本机 CachyOS / EndeavourOS DKMS 集成

此目录只属于 local/cachyos-dkms 分支，**不包含在贡献分支/PR**。

## 安装与布局

- gpu-unlock-4060-local/1.1.1.ad107.1 注册至 DKMS；模块仍名 gpu_unlock。
- 按目标内核 .config 判断 CONFIG_CC_IS_CLANG：Clang内核用LLVM=1，其他用默认GCC。
- MAKE 使用bash构建助手，防止DKMS在外层误加KERNELRELEASE；助手根据目标内核配置选择LLVM，GCC分支明确清空LLVM。
- AUTOINSTALL=yes，利用系统现有70-dkms hooks为后续已安装headers的新内核构建。
- 固定版本固件留在 /usr/lib/firmware/gpu-unlock/610.43.03，不替换正常NVIDIA驱动固件。
- 不安装上游force_drivers dracut配置；普通系统镜像通过独立omit配置排除gpu_unlock。

管理员运行（参数须为9个已校验资源的目录）：

```bash
sudo bash local/cachyos/install-host.sh /absolute/path/to/verified/assets
```

只注册、编译、安装模块与固件，不modprobe/rmmod、不重建镜像、不改GRUB、不重启。失败可能留下已注册或部分编译内核，应检查dkms status和/var/lib/dkms/gpu-unlock-4060-local，不在失败后盲目覆盖重试。

## 当前TEST与安装后模块

现有已验证TEST镜像仍包含它原来那份模块，安装DKMS不会替换嵌入副本。贡献源码不带ad107_result接口，本地分支追加了该状态及验证过的initrd gate（位于local/cachyos/image-overlay）。因此主机安装和测试镜像的源码提交/哈希需分别记录；不要混称已经启动验证了新的DKMS产物。

## 更新规则

- 系统内核升级：DKMS自动编译，但必须检查状态和构建日志；工具链/headers/内核API变化可能导致失败。
- **不自动更新解锁镜像和GRUB**。现有TEST固定旧内核/镜像，旧内核模块目录被移除后不要使用它。内核升级后应使用新的匹配模块重新构建独立镜像并审计，再手动添加新入口。
- 普通系统镜像不应含gpu_unlock；安装了root模块不意味着它会自动执行。不要把它加入全局modules-load或普通force_drivers。
- 不支持承诺休眠、runtime D3/独显断电保持。没有自动重试或复位策略。
- Git项目更新要显式pull/rebase并安装新版本；DKMS不拉取Git。升级时递增本地版本，不能只改工作树而保留版本号。

## 卸载

```bash
sudo bash local/cachyos/uninstall-host.sh
```

移除本地DKMS注册/源码/omit配置，不卸载正在运行的模块，不删除固件、旧TEST镜像或GRUB项。固件和启动文件需确认无其他用途后单独清理。默认启动和恢复入口从不修改。

## 保留边界

这是本机维护方案，不宣称通用安装器。上游提供显卡支持；本分支提供主机编译/安装。内核更新后要检查独立启动镜像，不能将AUTOINSTALL等同于已验证自动解锁升级。

## 本机安装记录（2026-10-25）

DKMS已为7.2.11-arch1-1(GCC)及7.3.0-4-cachyos(LLVM)实际编译、MOK签名并安装。完整资源回归31项、3项可选依赖跳过；编译器选择模拟3项通过。原始及TEST镜像哈希未变；当前已加载模块仍来自之前验证过的TEST，不宣称新DKMS产物已启动验证。

这次安装仅为DKMS注册，不是pacman包，因此pacman不跟踪这些手动安装文件；本分支脚本负责卸载。后续系统内核包更新会由现有DKMS hooks找到/usr/src的注册模块。镜像/GRUB仍需显式维护，未设置自动重启/自动切默认项。

## 独立镜像自动更新（本分支后续实现）

前文“不自动更新镜像/GRUB”描述基础DKMS安装阶段。额外执行 `install-auto-update.sh` 后，以下新流程取代手动维护：

- root专用运行文件安装在 `/usr/local/lib/gpu-unlock-4060/`，不依赖外接磁盘或Git工作区。
- 本机rootUUID/启动参数留在 `/etc/gpu-unlock-4060.conf`，不提交。
- `/etc/pacman.d/hooks/99-gpu-unlock-4060.hook` 在当前70-DKMS及90-dracut之后运行；默认仅处理linux-cachyos包内核。
- 每次核对DKMS installed状态、目标vermagic和结果接口，从已安装签名压缩模块取规范化字节作校验；固定固件核对9个SHA。
- 构建版本化独立镜像与内核副本，排除抢先绑定驱动、保留门控；镜像审计通过才原子更新独立菜单 `/boot/grub/gpu-unlock-4060.cfg`。
- 已有custom.cfg只新增受标记的source块，TEST原文保留；不改grub.cfg/default/grub或默认选择，不调用reboot/modprobe。
- 当前布局仅支持ext4根分区同时包含/boot。新菜单检查对应内核pkgbase仍存在，避免显示已移除内核；这不等于保证其NVIDIA驱动一定成功。
- 钩子失败不能回滚pacman更新，会保留之前菜单/已生成文件；此前内核被移除时旧项不一定可用。请检查更新输出和 `/var/log/gpu-unlock-4060/`，不能忽略构建失败。
- 更新器不会自动清理历史镜像，防止误删恢复文件；定期检查/boot空间。

管理员安装自动化：

```bash
sudo bash local/cachyos/install-auto-update.sh
```

手动DKMS升级/改变root配置不触发pacman hook，之后需明确运行 `/usr/local/lib/gpu-unlock-4060/update-images.sh`。此命令只构建发布，不启动。Git pull不会自动更新root-owned已安装工具，需审查后显式升级工具副本。

自动化可停止：删除本地99-gpu-unlock-4060.hook后不再自动构建（不影响已存在入口）；卸载DKMS之前应同时停止此钩子并移除managed source块。仍保留原始正常入口。休眠/runtime-D3边界不变。

本机已手动执行更新器成功：新DKMS菜单已发布、图像审计通过；未实际模拟pacman内核升级，未启动新DKMS入口。旧TEST及默认保持。后续仍需一次新入口启动验证。
