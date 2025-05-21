
-- Create the database
CREATE DATABASE IF NOT EXISTS food_waste_management;
USE food_waste_management;

-- Users table
CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    contact VARCHAR(20),
    address TEXT,
    role ENUM('restaurant', 'ngo', 'admin') NOT NULL DEFAULT 'restaurant',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Food Donations table
CREATE TABLE Food_Donations (
    donation_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    food_name VARCHAR(100) NOT NULL,
    quantity VARCHAR(50),
    pickup_location TEXT NOT NULL,
    contact VARCHAR(20),
    status ENUM('available', 'picked_up', 'cancelled') DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id)
);

-- Pickups table
CREATE TABLE Pickups (
    pickup_id INT AUTO_INCREMENT PRIMARY KEY,
    donation_id INT NOT NULL,
    receiver_id INT NOT NULL,
    pickup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('pending', 'completed', 'cancelled') DEFAULT 'pending',
    FOREIGN KEY (donation_id) REFERENCES Food_Donations(donation_id),
    FOREIGN KEY (receiver_id) REFERENCES Users(user_id)
);

-- Sample Users
INSERT INTO Users (name, email, password, contact, address, role) VALUES
('Green Leaf Restaurant', 'greenleaf@gmail.com', 'hashedpassword123', '9800001111', 'Main Street, Biratnagar', 'restaurant'),
('Helping Hands NGO', 'helpinghands@gmail.com', 'hashedpassword456', '9800002222', 'College Road, Itahari', 'ngo');

-- Sample Food Donations
INSERT INTO Food_Donations (user_id, food_name, quantity, pickup_location, contact) VALUES
(1, 'Vegetable Biryani', '10 servings', 'Green Leaf Restaurant, Main Street', '9800001111'),
(1, 'Dal Bhat Set', '15 plates', 'Green Leaf Restaurant, Main Street', '9800001111');

-- Sample Pickups
INSERT INTO Pickups (donation_id, receiver_id, status) VALUES
(1, 2, 'completed'),
(2, 2, 'pending');
