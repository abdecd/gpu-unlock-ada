# 本机 DKMS 与解锁镜像

分支：`local/cachyos-dkms`。通用显卡支持位于 `contrib/ad107-4060-laptop`，不包含本机安装配置。

## 安装

在仓库根目录运行。需要目标内核的 headers、DKMS、Clang/LLVM、dracut、Python、zstd。

```bash
# 下载、校验并生成固定版本固件
make assets

# 首次安装模块和固件；已有安装会拒绝覆盖
sudo bash local/cachyos/install-host.sh "$HOME/.cache/gpu-unlock/assets"

# 安装镜像更新工具和 pacman 钩子，并构建解锁镜像
sudo bash local/cachyos/install-auto-update.sh
```

安装不会加载模块、修改 GRUB 或重启。DKMS 根据目标内核选择 GCC 或 LLVM。

## 自动更新

系统 DKMS 为有 headers 的内核编译模块。随后本地 `99-gpu-unlock-4060.hook` 为每个已安装内核生成：

```text
/boot/initramfs-<内核包名>-nvidia-40-unlock.img
```

例如：

```text
/boot/initramfs-linux-nvidia-40-unlock.img
/boot/initramfs-linux-cachyos-nvidia-40-unlock.img
```

构建并审计通过后才替换同名解锁镜像。普通和 fallback 镜像不变，GRUB 由用户维护。

失败时保留旧解锁镜像并报错；旧镜像可能不匹配新内核，修复前使用普通入口。日志：`/var/log/gpu-unlock-4060/`。

手动重建：

```bash
sudo /usr/local/lib/gpu-unlock-4060/update-images.sh
```

Git 更新不会自动更新已安装工具；手动修改 DKMS 后也需重新构建镜像。同名内核包对应多个版本时，更新器拒绝生成歧义文件。

## GRUB

复制正常启动项，保留根分区、其他参数及微码配置，配对对应内核和解锁镜像：

```text
linux  /boot/vmlinuz-linux-cachyos 原有参数 gpu_unlock.targets=0000:01:00.0 gpu_unlock.ad107_experimental=1
initrd /boot/initramfs-linux-cachyos-nvidia-40-unlock.img
```

普通 Arch 内核对应 `vmlinuz-linux` 和 `initramfs-linux-nvidia-40-unlock.img`。示例中的“原有参数”需要替换；路径取决于 `/boot` 布局。

本机可编辑 `/boot/grub/custom.cfg`，无需重新生成主配置。若使用 `/etc/grub.d/40_custom`，需自行运行 `grub-mkconfig`。保留一个不解锁的正常入口。

## 卸载

先查看操作：

```bash
sudo bash local/cachyos/uninstall-host.sh --dry-run
```

默认卸载自动更新钩子、DKMS、源码、工具、专用配置和哈希匹配的固定固件：

```bash
sudo bash local/cachyos/uninstall-host.sh
```

同时清理有校验记录且内容匹配的解锁镜像和日志：

```bash
sudo bash local/cachyos/uninstall-host.sh --purge-images --purge-logs
```

可单独使用 `--purge-images` 或 `--purge-logs`。镜像或固件被修改时拒绝删除，避免误删其他文件。

卸载不修改用户 GRUB，不删除普通/fallback 镜像、旧 TEST 文件、备份或仓库。自行移除无用菜单项。不会执行 `rmmod` 或重启；已加载模块和运行时状态留到关机，下次选择普通入口。钩子移除后不再自动生成镜像。

## 安装位置

| 内容 | 路径 |
|---|---|
| DKMS 源码 | `/usr/src/gpu-unlock-4060-local-1.1.1.ad107.1` |
| 固定固件 | `/usr/lib/firmware/gpu-unlock/610.43.03` |
| 更新工具 | `/usr/local/lib/gpu-unlock-4060` |
| pacman 钩子 | `/etc/pacman.d/hooks/99-gpu-unlock-4060.hook` |
| 普通镜像排除配置 | `/etc/dracut.conf.d/zz-gpu-unlock-local-stock-omit.conf` |

## 范围

本机已验证两次实验解锁和一次原始入口恢复，双内核 DKMS 编译及独立镜像审计通过。新镜像和真实系统升级流程仍需启动验证。未验证休眠、运行时独显断电恢复及长时间应用稳定性。
