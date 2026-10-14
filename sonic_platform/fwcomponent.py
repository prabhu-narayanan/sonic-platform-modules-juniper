from sonic_platform_base.component_base import ComponentBase


class FwComponent(ComponentBase):
    """
    Component class that wraps FwCompInv inventory objects.
    This allows the sonic_platform to work with inventory-based
    firmware component definitions.
    """

    def __init__(self, fw_inv_obj):
        super().__init__()
        from sonic_platform.override import load_impl
        self._impl = load_impl("FwComponent", self)
        self._fw = fw_inv_obj

    def get_firmware_version(self):
        return self._impl.get_firmware_version()

    def install_firmware(self, image_path):
        return self._impl.install_firmware(image_path)

    def get_name(self):
        return self._impl.get_name()

    def get_description(self):
        return self._impl.get_description()

    def update_firmware(self, image_path):
        return self._impl.update_firmware(image_path)

    def get_available_firmware_version(self, image_path):
        return self._impl.get_available_firmware_version(image_path)

    def get_presence(self):
        return self._impl.get_presence()

    def get_status(self):
        return self._impl.get_status()

    def auto_update_firmware(self, image_path, boot_type):
        return self._impl.auto_update_firmware(image_path, boot_type)

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def get_revision(self):
        return self._impl.get_revision()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()

    def is_replaceable(self):
        return self._impl.is_replaceable()

