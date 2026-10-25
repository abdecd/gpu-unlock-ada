# 本机 DKMS + 每内核独立解锁镜像（GRUB由用户维护）

仅属于local/cachyos-dkms分支，不包含在贡献分支。

## 最终职责

1. 系统DKMS hooks自动为有headers的内核编译gpu-unlock-4060-local/1.1.1.ad107.1；目标Clang内核用LLVM，GCC内核清空LLVM。
2. 本地99-gpu-unlock-4060.hook在当前70-DKMS及90-dracut之后，执行root-owned `/usr/local/lib/gpu-unlock-4060/update-images.sh`。
3. 更新器枚举所有具备pkgbase/vmlinuz的已安装linux系列内核，要求headers、DKMS installed、vermagic和本地结果接口匹配，构建审计独立镜像。
4. 输出 `/boot/initramfs-<pkgbase>-nvidia-40-unlock.img`。先构建临时文件、审计、同文件系统暂存校验，再原子替换同名unlock文件。
5. **绝不生成/改写GRUB菜单，不复制专用内核，不改默认项，不改普通或fallback镜像。** 用户配置最后一步。

本机对应：
- linux 7.2.11-arch1-1 → /boot/initramfs-linux-nvidia-40-unlock.img
- linux-cachyos 7.3.0-4-cachyos → /boot/initramfs-linux-cachyos-nvidia-40-unlock.img

相同pkgbase同时出现多个版本时拒绝，避免固定文件名歧义。无headers/模块编译失败时保留旧unlock并报错；旧镜像可能不匹配升级后的内核，不能因为文件存在就继续启动。

## 安装与手动触发

基础DKMS安装（首次，没有现存版本时）：
```bash
sudo bash local/cachyos/install-host.sh /absolute/path/to/verified/assets
```
安装/升级镜像自动化：
```bash
sudo bash local/cachyos/install-auto-update.sh
```
手动重建所有已安装内核的unlock镜像：
```bash
sudo /usr/local/lib/gpu-unlock-4060/update-images.sh
```
均不加载/重载模块，不重启。安装脚本不是pacman包，文件由本地脚本管理。运行时资源在root-owned目录，不依赖/run/media挂载或Git工作区。

固定固件路径 /usr/lib/firmware/gpu-unlock/610.43.03，9个SHA固定。普通dracut通过/etc/dracut.conf.d/zz-gpu-unlock-local-stock-omit.conf只排除gpu_unlock，正常NVIDIA不受影响。独立镜像使用专用confdir绕开此项并排除提前绑定驱动；门控要求精确28a0与完整BDF、单次执行、结果3，不支持自动重试。

## GRUB由你配置

从正常入口复制一个解锁项，保留root、其他参数与微码；按内核包名配对：

```text
linux  /boot/vmlinuz-linux-cachyos 原有参数 gpu_unlock.targets=0000:01:00.0 gpu_unlock.ad107_experimental=1
initrd /boot/initramfs-linux-cachyos-nvidia-40-unlock.img
```

普通Arch对应vmlinuz-linux + initramfs-linux-nvidia-40-unlock.img。这些是结构示例，不要把“原有参数”原样粘贴。GRUB文件路径取决于/boot布局。当前本机/boot在ext4根分区。用户可用/boot/grub/custom.cfg或40_custom，自行管理。不运行grub-mkconfig也不改任何默认项的责任由更新器保持。

## 自动更新边界

内核/headers/固件/systemd/dracut等pacman事件会触发本地钩子，当前钩子顺序与系统匹配。钩子失败不能回滚pacman；必须查看报错和/var/log/gpu-unlock-4060。未实际模拟完整pacman升级，已实际执行双内核构建/审计通过。普通Arch新解锁镜像未实机启动验证，CachyOS新DKMS镜像也不等于旧TEST已启动验证。

不自动清理已卸载内核的unlock镜像（避免误删）；用户应清理无用镜像/菜单。Git pull或手动DKMS改动不触发pacman hook，需显式重新安装工具并运行更新器。模块版本变化要更新本地版本及工具的匹配规则。

## 卸载与恢复

先正常入口启动。停止自动构建可移除/etc/pacman.d/hooks/99-gpu-unlock-4060.hook；再卸载本地DKMS注册/源码。uninstall-host.sh不卸载正在运行模块、不删除固件、镜像或用户菜单。用户自行清理确认不再需要的-unlock.img，原始镜像始终保留。

本次旧TEST/DKMS生成菜单已备份并清理。旧版本化实验内核/镜像暂留备份，不再引用；可确认新入口成功后再删除。

## 验证与限制

两个内核实际DKMS编译签名安装成功，两个固定名unlock镜像实际构建并审计通过。全资源回归31项/3可选跳过；工具测试见local/cachyos/tests。未重启、未切默认、未重载当前模块。运行时D3/独显断电、休眠恢复和长期应用稳定性未承诺。
