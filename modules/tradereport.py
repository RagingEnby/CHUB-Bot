from typing import Optional, Literal, Any
import aiohttp
import disnake
import aiofiles
import json

from modules import mojang
from modules import misc

import datatypes
import config

BUTTON_ID = 'TradeReport'


PENDING_REPORTS: dict[str, datatypes.TradeReport] = {
    id_: datatypes.TradeReport.from_dict(trade)
    for id_, trade in json.load(open(config.TRADE_REPORT_FILE_PATH, 'r')).items()
}
INACTIVE_COMPONENTS: list[disnake.ui.Button] = [
    disnake.ui.Button(
        emoji=":ballot_box_with_check:",
        style=disnake.ButtonStyle.green,
        disabled=True
    ),
    disnake.ui.Button(
        emoji=":regional_indicator_x:",
        style=disnake.ButtonStyle.red,
        disabled=True
    )
]


class VerificationModal(disnake.ui.Modal):
    def __init__(self, trade: datatypes.TradeReport, buyer: str, seller: str, date: str, item: str, price: str):
        self.trade = trade
        components = [
            disnake.ui.TextInput(
                label="Buyer",
                custom_id="buyer",
                style=disnake.TextInputStyle.short,
                min_length=2, max_length=32,
                placeholder=buyer
            ),
            disnake.ui.TextInput(
                label="Seller",
                custom_id="seller",
                style=disnake.TextInputStyle.short,
                min_length=2, max_length=32,
                placeholder=seller
            ),
            disnake.ui.TextInput(
                label="Date",
                custom_id="date",
                style=disnake.TextInputStyle.short,
                min_length=2, max_length=32,
                placeholder=date
            ),
            disnake.ui.TextInput(
                label="Item",
                custom_id="item",
                style=disnake.TextInputStyle.short,
                min_length=2, max_length=32,
                placeholder=item
            ),
            disnake.ui.TextInput(
                label="Price",
                custom_id="price",
                style=disnake.TextInputStyle.short,
                min_length=2, max_length=32,
                placeholder=price
            ),
            disnake.ui.TextInput(
                label="Overpay/Underpay",
                custom_id="overpay_underpay",
                style=disnake.TextInputStyle.short,
                placeholder="ENTER: 'over', 'under', or 'N/A'"
            )
        ]
        super().__init__(title="Send Trade Report", custom_id="send_trade_report", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer()
        if not inter.user.get_role(config.RECENT_SALES_JURY_ROLE):
            return await inter.send(embed=misc.make_error(
                "No Permissions",
                f"You must have the <@&{config.RECENT_SALES_JURY_ROLE}> role to send trade reports"
            ))
            
        if inter.text_values["overay_underpay"] not in ['over', 'under', 'N/A']:
            return await inter.send(embed=misc.make_error(
                "Invalid Overpay/Underpay value",
                f"You entered `{disnake.utils.escape_markdown(inter.text_values['overpay_underpay'])}`"
                " but it must be equal to `over`, `under`, or `N/A`"
            ))

        overpay_underpay = inter.text_values["overpay_underpay"] if inter.text_values["overpay_underpay"] != 'N/A' else None

        censor = '||' if overpay_underpay else ''
        content = censor + '\n'.join([
            "# " + overpay_underpay.upper() if overpay_underpay else '',
            f"**Buyer:** {inter.text_values['buyer']}",
            f"**Seller:** {inter.text_values['seller']}",
            f"**Date:** {inter.text_values['date']}",
            f"**Item:** {inter.text_values['item']}",
            f"**Price:** {inter.text_values['price']}",
        ]) + censor
        channel = inter.bot.get_channel(config.TRADE_REPORT_CHANNEL)
        await channel.send(content, file=self.trade.image.file)


async def save_pending_reports():
    async with aiofiles.open(config.TRADE_REPORT_FILE_PATH, 'w') as file:
        await file.write(json.dumps({k: v.to_dict() for k, v in PENDING_REPORTS.items()}))


async def log_trade_report(report: datatypes.TradeReport):
    PENDING_REPORTS[report.id] = report
    await save_pending_reports()


async def on_button_click(inter: disnake.MessageInteraction, button_data: str):
    button_data: dict[str, Any] = json.loads(button_data)
    trade_report: Optional[datatypes.TradeReport] = PENDING_REPORTS.pop(button_data['id'], None)
    if trade_report is None:
        return await inter.send(embed=misc.make_error(
            "Invalid Trade",
            f"No trade with the ID `{disnake.utils.escape_markdown(button_data['id'])}`. This is likely because the trade has already been accepted or denied"
        ))
    author = inter.bot.get_user(trade_report.author) if trade_report.author else None
    
    if button_data['action'] == 'accept':
        await inter.message.edit(
            embed=trade_report.to_embed(status='accepted'),
            components=INACTIVE_COMPONENTS
        )
        return await inter.response.send_modal(VerificationModal(
            trade=trade_report,
            buyer=trade_report.buyer.name,
            seller=trade_report.seller.name,
            date=trade_report.date,
            item=trade_report.item,
            price=trade_report.price
        ))
    # IMPLIMENT DENYING LATER, THIS IS UNFINSHED


async def send_log_msg(inter: disnake.AppCmdInter, report: datatypes.TradeReport):
    channel = inter.bot.get_channel(config.TRADE_REPORT_VERIFICATION_CHANNEL)
    await channel.send()


async def report_trade_command(
    inter: disnake.AppCmdInter,
    seller_name: str,
    buyer_name: str,
    date: str,
    item: str,
    price: str,
    payment_type: datatypes.TradePaymentType,
    image: disnake.Attachment,
    notes: Optional[str]
):
    await inter.response.defer()
    if seller_name == buyer_name:
        return await inter.send(embed=misc.make_error(
            "Invalid Trade",
            "You cannot trade with yourself!"
        ))
        
    async with aiohttp.ClientSession() as session:
        seller = await mojang.get(seller_name, session=session)
        if seller is None:
            return await inter.send(embed=misc.make_error(
                "Invalid Seller",
                f"`{disnake.utils.escape_markdown(seller_name)}` is not a valid Minecraft IGN."
            ))
        buyer = await mojang.get(buyer_name, session=session)
        if buyer is None:
            return await inter.send(embed=misc.make_error(
                "Invalid Buyer",
                f"`{disnake.utils.escape_markdown(buyer_name)}` is not a valid Minecraft IGN."
            ))

        
        trade_report = datatypes.TradeReport(
            author=inter.user.id,
            seller=seller,
            buyer=buyer,
            date=date,
            item=item,
            price=price,
            payment_type=payment_type,
            image=datatypes.TradeReportAttachment.from_disnake_attachment(image),
            notes=notes
        )
        await log_trade_report(trade_report)
        
        channel = inter.bot.get_channel(config.TRADE_REPORT_VERIFICATION_CHANNEL)
        await channel.send(
            embed=trade_report.to_embed(),
            components=[
                disnake.ui.Button(
                    emoji=":ballot_box_with_check:",
                    style=disnake.ButtonStyle.green,
                    custom_id=f"{BUTTON_ID}|{json.dumps({'action': 'accept', 'id': trade_report.id})}"
                ),
                disnake.ui.Button(
                    emoji=":regional_indicator_x:",
                    style=disnake.ButtonStyle.red,
                    custom_id=f"{BUTTON_ID}|{json.dumps({'action': 'deny', 'id': trade_report.id})}"
                )
            ]
        )
        