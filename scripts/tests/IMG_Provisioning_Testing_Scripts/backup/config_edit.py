import os
from datetime import datetime

CONFIG_FILE = "config.txt"

class ProvisioningConfig():

    def read_config(self):
        """Read the config file and return values as dict"""
        if not os.path.exists(CONFIG_FILE):
            return {
                "previous_gateway": "00000000",
                "current_gateway": "00000000",
                "previous_sink": "00000000",
                "current_sink": "00000000"
            }

        with open(CONFIG_FILE, "r") as f:
            lines = f.readlines()

        config = {}
        for line in lines:
            if "previous gateway id" in line:
                config["previous_gateway"] = line.split("=")[1].strip()
            elif "current gateway id" in line:
                config["current_gateway"] = line.split("=")[1].strip()
            elif "previous sink id" in line:
                config["previous_sink"] = line.split("=")[1].strip()
            elif "current sink id" in line:
                config["current_sink"] = line.split("=")[1].strip()

        return config

    def get_next_id(self, current_id, prefix=""):
        """Generate next ID based on current_id"""
        year = datetime.now().year % 100 

        if current_id == "00000000":
            next_num = 1
        else:
            # Extract the last number part
            num_part = ''.join(filter(str.isdigit, current_id))
            next_num = int(num_part[-6:]) + 1  # last 6 digits

        return f"{prefix}{year}{next_num:06d}"

    def update_config(self):
        config = self.read_config()

        # Move current -> previous
        config["previous_gateway"] = config["current_gateway"]
        config["previous_sink"] = config["current_sink"]

        # Generate new current IDs
        config["current_gateway"] = self.get_next_id(config["current_gateway"], "IMG")
        config["current_sink"] = self.get_next_id(config["current_sink"], "")

        # Write back to file
        with open(CONFIG_FILE, "w") as f:
            f.write(f"previous gateway id = {config['previous_gateway']}\n")
            f.write(f"current gateway id = {config['current_gateway']}\n")
            f.write(f"previous sink id = {config['previous_sink']}\n")
            f.write(f"current sink id = {config['current_sink']}\n")

        return config


if __name__ == "__main__":
    prob_config = ProvisioningConfig()
    new_config = prob_config.update_config()
    print("Updated config:")
    for k, v in new_config.items():
        print(f"{k}: {v}")
