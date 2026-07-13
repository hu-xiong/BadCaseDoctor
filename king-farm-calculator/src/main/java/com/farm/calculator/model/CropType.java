package com.farm.calculator.model;

/**
 * 王者荣耀农场作物类型
 * 基于游戏实际数据：浇水后成熟时间 = 原周期 x 11/15
 */
public enum CropType {
    // 1小时作物
    SUNFLOWER("向日葵", 60, 1, 12),
    WHEAT("小麦", 60, 1, 1),
    CARROT("胡萝卜", 60, 1, 1),

    // 8小时作物
    GREEN_PEPPER("青椒", 480, 8, 9),
    CORN("玉米", 480, 8, 9),
    GARLIC("大蒜", 480, 8, 9),
    STRAWBERRY("草莓", 480, 8, 12),

    // 16小时作物
    BANANA("香蕉", 960, 16, 18),
    POMELO("柚子", 960, 16, 28),
    TOMATO("番茄", 960, 16, 18),
    POTATO("土豆", 960, 16, 14),
    WATERMELON("西瓜", 960, 16, 38),

    // 32小时作物
    GRAPE("葡萄", 1920, 32, 20),
    BLUEBERRY("蓝莓", 1920, 32, 20),
    CABBAGE("卷心菜", 1920, 32, 26),
    KIWI("猕猴桃", 1920, 32, 38),
    CHERRY("樱桃", 1920, 32, 38);

    private final String displayName;
    /** 原生长周期（分钟） */
    private final int growthMinutes;
    /** 原生长周期（小时） */
    private final int growthHours;
    /** 解锁等级 */
    private final int unlockLevel;

    CropType(String displayName, int growthMinutes, int growthHours, int unlockLevel) {
        this.displayName = displayName;
        this.growthMinutes = growthMinutes;
        this.growthHours = growthHours;
        this.unlockLevel = unlockLevel;
    }

    public String getDisplayName() { return displayName; }
    public int getGrowthMinutes() { return growthMinutes; }
    public int getGrowthHours() { return growthHours; }
    public int getUnlockLevel() { return unlockLevel; }

    /**
     * 浇水后最短成熟时间（分钟）
     * 公式：原周期 x 11/15
     */
    public int getMinWateredMinutes() {
        return (int) Math.round(growthMinutes * 11.0 / 15.0);
    }

    /**
     * 获取浇水时间节点（分钟，从播种算起）
     * 节点：0, T/3, 2T/3, 11T/15
     */
    public int[] getWateringNodes() {
        return new int[]{
                0,
                growthMinutes / 3,
                growthMinutes * 2 / 3,
                (int) Math.round(growthMinutes * 11.0 / 15.0)
        };
    }

    /** 备注文字，显示在界面上 */
    public String getNodeLabel(int index) {
        int[] nodes = getWateringNodes();
        if (index < 0 || index >= nodes.length) return "";
        int mins = nodes[index];
        if (mins < 60) return mins + "分钟";
        int h = mins / 60;
        int m = mins % 60;
        return h + "小时" + (m > 0 ? m + "分" : "");
    }
}
