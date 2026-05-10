import matplotlib.pyplot as plt
import os
from pathlib import Path

class TrainingVisualizer:
    def __init__(self, save_dir):
        """
        Initialize the TrainingVisualizer.
        
        Args:
            save_dir (str or Path): The directory where the plot will be saved.
        """
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.epochs = []
        self.train_losses = []
        self.val_losses = []

    def update(self, epoch, train_loss, val_loss):
        """
        Update the training history and regenerate the plot.
        
        Args:
            epoch (int): Current epoch number.
            train_loss (float): Training loss for the current epoch.
            val_loss (float): Validation loss for the current epoch.
        """
        self.epochs.append(epoch)
        self.train_losses.append(train_loss)
        self.val_losses.append(val_loss)
        self.plot()

    def plot(self):
        """
        Generate and save the loss plot.
        """
        plt.figure(figsize=(10, 6))
        plt.plot(self.epochs, self.train_losses, label='Train Loss', marker='o')
        plt.plot(self.epochs, self.val_losses, label='Validation Loss', marker='o')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.title('Training and Validation Loss Over Epochs')
        plt.legend()
        plt.grid(True)
        
        output_path = self.save_dir / 'training_loss_curve.png'
        plt.savefig(output_path)
        plt.close()
